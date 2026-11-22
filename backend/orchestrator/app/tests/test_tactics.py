"""Pronóstico del final y recomendación de adelantamientos (sin estado, sobre /athletes)."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.cv.tactics.forecast import FinishForecaster, ForecastConfig
from app.cv.tactics.overtake import OvertakeAdvisor, OvertakeConfig

FPS = 10


def _frames(secs: float = 20.0, t0: float = 0.0, speeds=(6.6, 6.6, 6.0)) -> list[dict]:
    """Tres atletas: #1 y #2 pegados al frente (el #1 dos metros adelante), #3 más atrás y lento."""
    starts = (100.0, 98.0, 80.0)
    lanes = (1.0, 1.0, 2.0)
    frames = []
    for k in range(int(secs * FPS)):
        t = t0 + k / FPS
        frames.append(
            {
                "t": round(t, 3),
                "athletes": [
                    {
                        "id": i + 1,
                        "x": starts[i] + speeds[i] * (t - t0),
                        "v": speeds[i],
                        "d": lanes[i],
                        "sigma_x": 0.4,
                    }
                    for i in range(3)
                ],
            }
        )
    return frames


def test_forecast_orders_by_pace_and_probabilities_add_up() -> None:
    f = FinishForecaster(ForecastConfig(distance=1500), seed=0)
    for fr in _frames():
        f.observe(fr["t"], fr["athletes"])
    out = f.forecast(19.9)

    assert out["athletes"][0]["id"] == 1  # va primero y al mismo ritmo
    assert out["athletes"][-1]["id"] == 3
    assert sum(a["p_win"] for a in out["athletes"]) == pytest.approx(1.0, abs=0.01)
    assert all(0 <= a["p_podium"] <= 1 for a in out["athletes"])
    for a in out["athletes"]:
        lo, mid, hi = a["eta"]
        assert lo <= mid <= hi
    assert out["winner"][0] <= out["winner"][1] <= out["winner"][2]


def test_forecast_unknown_distance_falls_back_instead_of_failing() -> None:
    cfg = ForecastConfig(distance=1234)
    lo, sd = cfg.level_prior()
    assert lo > 0 and sd > 0


def test_forecast_finished_athlete_keeps_the_crossing_time() -> None:
    f = FinishForecaster(ForecastConfig(distance=100), seed=0)
    f.observe(0.0, [{"id": 1, "x": 90.0, "v": 10.0}])
    f.observe(2.0, [{"id": 1, "x": 110.0, "v": 10.0}])
    out = f.forecast(2.0)
    assert out["athletes"][0]["eta"] == [1.0, 1.0, 1.0]
    assert out["athletes"][0]["p_win"] == 1.0


def test_overtake_gap_and_ahead_rival() -> None:
    adv = OvertakeAdvisor(OvertakeConfig(distance=1500), ForecastConfig(distance=1500), seed=0)
    for fr in _frames():
        adv.observe(fr["t"], fr["athletes"])
    t = 19.9
    assert adv.rival_ahead(2, t) == 1  # el #1 va 2 m adelante del #2
    assert adv.rival_ahead(1, t) is None  # nadie por delante a menos de 15 m

    rec = adv.recommend(2, t)
    assert rec is not None
    assert rec["rival"] == 1 and rec["action"] in {"attack", "wait", "hold"}
    assert 0 <= rec["p_attack"] <= 1 and rec["p_attack"] >= rec["p_now"] - 1e-9
    assert 1 <= rec["zone"] <= 6
    assert rec["window"][0] >= rec["window"][1]
    assert rec["gap"] == pytest.approx(2.0, abs=0.3)
    assert rec["curve"][0][0] == rec["remaining"]


def test_overtake_pass_in_a_curve_costs_extra_meters() -> None:
    """Pasar por fuera en curva suma metros; en recta, no."""
    adv = OvertakeAdvisor(OvertakeConfig(distance=1500), ForecastConfig(distance=1500), seed=0)
    for fr in _frames():
        adv.observe(fr["t"], fr["athletes"])
    curve = adv.duel(2, 1)["curve"]
    assert any(p["extra"] > 0 for p in curve)
    assert any(p["extra"] == 0 for p in curve)


def test_tactics_endpoint_contract(client: TestClient) -> None:
    body = {
        "distance": 1500,
        "t0": 0.0,
        "every_s": 1.0,
        "frames": _frames(),
    }
    first = client.post("/api/tactics/", json=body)

    assert first.status_code == 200, first.text
    data = first.json()
    assert data["distance"] == 1500 and data["disclaimer"]
    steps = data["steps"]
    assert 15 <= len(steps) <= 21  # un paso por segundo en 20 s
    assert [s["t"] for s in steps] == sorted(s["t"] for s in steps)
    last = steps[-1]
    assert {a["id"] for a in last["athletes"]} == {1, 2, 3}
    assert last["winner"] is not None
    assert len(last["attacks"]) <= 3
    assert all(a["rival"] != a["id"] for a in last["attacks"])
    # determinista: misma entrada, misma salida
    assert client.post("/api/tactics/", json=body).json() == data


def test_tactics_eta_is_on_the_race_clock(client: TestClient) -> None:
    """Con el disparo en t0, la llegada se cuenta desde el disparo y no desde el inicio del video."""
    base = client.post(
        "/api/tactics/", json={"distance": 1500, "frames": _frames(t0=0.0), "every_s": 5}
    ).json()
    shifted = client.post(
        "/api/tactics/",
        json={"distance": 1500, "t0": 3.0, "frames": _frames(t0=3.0), "every_s": 5},
    ).json()

    a = base["steps"][0]["winner"][1]
    b = shifted["steps"][0]["winner"][1]
    assert b == pytest.approx(a, abs=15)  # misma carrera: el reloj no se corre 3 s de más
    assert shifted["steps"][0]["t"] >= 3.0


def test_tactics_skips_frames_without_measured_athletes(client: TestClient) -> None:
    frames = [{"t": round(k / FPS, 3), "athletes": []} for k in range(5)]
    response = client.post("/api/tactics/", json={"distance": 1500, "frames": frames})
    assert response.status_code == 200
    assert response.json()["steps"] == []


def test_tactics_requires_increasing_time(client: TestClient) -> None:
    frames = _frames(secs=1)
    frames[3]["t"] = frames[2]["t"]
    response = client.post("/api/tactics/", json={"distance": 1500, "frames": frames})
    assert response.status_code in (400, 422)


def test_numpy_seed_is_independent_of_global_state() -> None:
    np.random.seed(1)
    a = FinishForecaster(ForecastConfig(), seed=3)
    np.random.seed(999)
    b = FinishForecaster(ForecastConfig(), seed=3)
    for fr in _frames(secs=2):
        a.observe(fr["t"], fr["athletes"])
        b.observe(fr["t"], fr["athletes"])
    assert a.forecast(1.9) == b.forecast(1.9)
