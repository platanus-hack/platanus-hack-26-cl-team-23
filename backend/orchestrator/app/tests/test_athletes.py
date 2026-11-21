import itertools
import json
import math
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.cv.athletes import pipeline
from app.cv.athletes.measure import (
    JERSEY_SIZE,
    LANE,
    _hsv_masks,
    fit_ppm,
    fit_view,
    lateral_measure,
    measure_frame,
    select_runners,
)
from app.cv.athletes.tracker import AthleteTracker, stable_order
from app.cv.zones.evidence import line_mask

GRASS, TARTAN, WHITE = (60, 130, 60), (40, 40, 190), (255, 255, 255)


def _lanes_image(lane_px: int = 40, n_lanes: int = 6, top: int = 200) -> np.ndarray:
    """Vista lateral sintética: pasto arriba (adentro), calles horizontales, el bordillo sin
    pintar (como la baranda de Hayward) y las líneas entre calles."""
    img = np.zeros((720, 1280, 3), np.uint8)
    img[:] = GRASS
    img[top : top + n_lanes * lane_px + 4] = TARTAN
    for k in range(1, n_lanes + 1):
        y = top + k * lane_px
        cv2.line(img, (0, y), (1279, y), WHITE, 3)
    return img


def _runner(img: np.ndarray, foot_x: int, foot_y: int, height: int, color) -> list[float]:
    w = int(0.4 * height)
    x1, y1 = foot_x - w // 2, foot_y - height
    img[y1 : foot_y - 2, x1 : x1 + w] = color
    return [float(x1), float(y1), float(x1 + w), float(foot_y)]


@pytest.mark.parametrize("alpha_deg,k", [(0, 0.15), (20, 0.3), (-35, 0.25)])
def test_fit_view_recovers_weak_perspective(alpha_deg: float, k: float) -> None:
    al, ppm = math.radians(alpha_deg), 100.0
    phi = math.atan2(k * math.sin(al), math.cos(al))
    sigma = ppm * k / math.sqrt(math.cos(al) ** 2 + k**2 * math.sin(al) ** 2)
    a2, k2 = fit_view(phi, ppm, sigma)
    assert abs(math.degrees(a2) - alpha_deg) < 3 and abs(k2 - k) / k < 0.1


def test_fit_ppm_is_robust_to_a_crouched_runner() -> None:
    y = np.array([300, 350, 400, 450, 500.0])
    h = 1.75 * (0.2 * y - 20)
    h[2] *= 0.7
    a, b = fit_ppm(y, h)
    assert abs(b - 0.2) < 0.02 and abs(a + 20) < 8


def test_select_runners_needs_feet_on_tartan() -> None:
    img = np.zeros((720, 1280, 3), np.uint8)
    img[:400], img[400:] = GRASS, TARTAN
    red, _ = _hsv_masks(img)
    boxes = np.array(
        [[100, 300, 150, 450], [300, 310, 350, 460], [500, 200, 550, 350], [700, 305, 750, 455.0]]
    )
    assert set(select_runners(boxes, red, ignore=[]).tolist()) == {0, 1, 3}


def test_lateral_counts_lanes_to_unpainted_kerb() -> None:
    lane_px = 40
    img = _lanes_image(lane_px)
    red, _ = _hsv_masks(img)
    mask = line_mask(img)
    foot = np.array([640.0, 200 + 1.5 * lane_px])
    r = lateral_measure(mask, red, np.zeros(mask.shape, bool), foot, 0.0, ppm=lane_px / LANE)
    assert r is not None and abs(r["lane_px"] - lane_px) < 3
    assert abs(r["d"] - 1.5 * LANE) < 0.35


def test_measure_frame_side_view() -> None:
    """Tres corredores de 1,75 m (= 70 px -> 40 px/m) en una toma lateral: Δs entre ellos
    = separación horizontal / 40 px/m, y d = calles hasta el bordillo."""
    lane_px, ppm = 40, 40.0
    img = _lanes_image(lane_px, top=200)
    boxes = [
        _runner(img, 400, 200 + int(0.5 * lane_px), 70, (200, 120, 30)),
        _runner(img, 560, 200 + int(1.5 * lane_px), 70, (30, 200, 200)),
        _runner(img, 720, 200 + int(0.5 * lane_px), 70, (90, 30, 160)),
    ]
    geo, meas = measure_frame(img, np.array(boxes))
    assert geo is not None and not geo.head_on and len(meas) == 3
    by_x = sorted(meas, key=lambda m: m["foot"][0])
    gaps = [b["ds"] - a["ds"] for a, b in itertools.pairwise(by_x)]
    assert all(abs(abs(g) - 160 / ppm) < 0.8 for g in gaps)
    ds = [m["d"] for m in by_x]
    assert all(d is not None for d in ds)
    assert ds[1] > ds[0] + 0.6 and ds[1] > ds[2] + 0.6


def test_tracker_group_plus_relative_and_reid_after_cut() -> None:
    """Grupo a 6,5 m/s; uno gana 0,5 m/s relativo. A mitad hay un corte: cambian los ids del
    tracker de imagen, pero los atletas se recuperan por posición y camiseta."""
    tracker = AthleteTracker(field_size=3)
    apps = [np.eye(JERSEY_SIZE, dtype=np.float32)[k] for k in (0, 10, 20)]
    xs0, rel_v = np.array([0.0, -2.0, -4.0]), np.array([0.0, 0.5, 0.0])
    ids_before = ids_after = None
    for k in range(300):
        t = k / 30
        x_true = 100 + 6.5 * t + xs0 + rel_v * t
        meas = [
            {
                "ds": float(x_true[j] - x_true.mean()),
                "sigma_ds": 0.3,
                "d": 0.5 + 1.2 * j,
                "sigma_d": 0.3,
            }
            for j in range(3)
        ]
        tids = [j + (100 if k >= 150 else 0) for j in range(3)]
        tracker.predict(t, 6.5)
        out = tracker.update(t, float(x_true.max()), meas, tids, apps, cut=k == 150)
        if k == 149:
            ids_before = [a.id for a in out]
        if k == 299:
            ids_after = [a.id for a in out]
    assert ids_before == ids_after
    a1 = tracker.ath[ids_after[1]]
    assert abs(a1.u - 0.5) < 0.25 and abs(6.5 + a1.u - 7.0) < 0.25
    assert abs(a1.d - 1.7) < 0.2


def test_field_size_caps_new_athletes() -> None:
    tracker = AthleteTracker(field_size=2)
    apps = [None, None]
    for k in range(10):
        tracker.predict(k * 0.1, 6.5)
        # el tracker de imagen inventa ids nuevos en cada frame (peor caso)
        tracker.update(
            k * 0.1,
            100 + 0.65 * k,
            [
                {"ds": 0.0, "sigma_ds": 0.3, "d": 0.5, "sigma_d": 0.3},
                {"ds": -2.0, "sigma_ds": 0.3, "d": 1.5, "sigma_d": 0.3},
            ],
            [10 * k, 10 * k + 1],
            apps,
            cut=True,
        )
    assert len(tracker.ath) == 2


def test_stable_order_needs_margin_to_swap() -> None:
    a, b = SimpleNamespace(id=1, x=100.0), SimpleNamespace(id=2, x=100.3)
    assert [q.id for q in stable_order([a, b], [1, 2])] == [1, 2]
    b.x = 100.6
    assert [q.id for q in stable_order([a, b], [1, 2])] == [2, 1]


def _synthetic_features(n: int = 60, dt: float = 1 / 15):
    """Dos corredores en toma lateral que la cámara sigue (el fondo se mueve -8 px/frame):
    'adelante' = hacia la derecha; el de la derecha va 3 m adelante."""
    feats = []
    for i in range(n):
        feats.append(
            pipeline.AthleteFrameFeatures(
                t=10.0 + i * dt,
                u_img=[1.0, 0.0],
                bg_shift=None if i == 0 else [-8.0, 0.0],
                runners=[
                    pipeline.RunnerFeatures(
                        1, [600, 300, 640, 400], [620, 400], 1.5, 0.3, 0.5, 0.3, None
                    ),
                    pipeline.RunnerFeatures(
                        2, [480, 300, 520, 400], [500, 400], -1.5, 0.3, 1.6, 0.3, None
                    ),
                ],
            )
        )
    return feats


def test_pipeline_forward_from_motion_and_ranks() -> None:
    feats = _synthetic_features()
    group = [pipeline.GroupState(x=200 + 6.6 * (f.t - 10.0), v=6.6) for f in feats]
    out = pipeline.run(feats, group, pipeline.AthleteParams(t0=0.0))
    last = out[-1]["athletes"]
    assert [a["rank"] for a in last] == [1, 2]
    lead, back = last
    assert lead["track_id"] == 1 and back["track_id"] == 2
    assert abs((lead["x"] - back["x"]) - 3.0) < 0.5
    assert abs(lead["x"] - group[-1].x) < 1.0
    assert lead["lane"] == 1 and back["lane"] == 2
    assert all(abs(a["v"] - 6.6) < 0.5 for a in last)


def test_s_counts_from_the_start_line_of_the_race() -> None:
    feats = _synthetic_features()
    group = [pipeline.GroupState(x=200 + 6.6 * (f.t - 10.0), v=6.6) for f in feats]
    # 1500 m: la salida está 100 m después de la meta; 800 m: sale en la meta
    for distance, s0 in ((1500, 100.0), (800, 0.0)):
        out = pipeline.run(feats, group, pipeline.AthleteParams(distance=distance))
        lead = out[-1]["athletes"][0]
        assert abs(lead["s"] - ((s0 + lead["x"]) % 400)) < 0.05


def _jpeg(img: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".jpg", img)
    assert ok
    return buffer.tobytes()


def test_features_endpoint(client: TestClient) -> None:
    img = _lanes_image(40)
    boxes = [_runner(img, 400, 220, 70, (200, 120, 30)), _runner(img, 560, 260, 70, (30, 200, 200))]
    files = [("frames", ("a.jpg", _jpeg(img), "image/jpeg")) for _ in range(2)]
    payload = json.dumps([[[7, *boxes[0]], [8, *boxes[1]]]] * 2)
    resp = client.post(
        "/api/athletes/features", files=files, data={"t": [0.0, 0.0667], "boxes": payload}
    )
    assert resp.status_code == 200, resp.text
    frames = resp.json()["frames"]
    assert len(frames) == 2 and frames[0]["bg_shift"] is None and frames[1]["bg_shift"] is not None
    runners = frames[0]["runners"]
    assert {r["id"] for r in runners} == {7, 8}
    assert all(r["jersey"] is None or len(r["jersey"]) == JERSEY_SIZE for r in runners)


def test_features_rejects_bad_boxes(client: TestClient) -> None:
    files = [("frames", ("a.jpg", _jpeg(_lanes_image()), "image/jpeg"))]
    resp = client.post(
        "/api/athletes/features", files=files, data={"t": [0.0], "boxes": "[[1,2,3]]"}
    )
    assert resp.status_code == 422


def test_athletes_endpoint_and_validation(client: TestClient) -> None:
    feats = _synthetic_features(30)
    frames = [
        {
            "t": f.t,
            "u_img": f.u_img,
            "head_on": False,
            "blind": False,
            "bg_shift": f.bg_shift,
            "runners": [
                {
                    "id": r.id,
                    "bbox": r.bbox,
                    "foot": r.foot,
                    "ds": r.ds,
                    "sigma_ds": r.sigma_ds,
                    "d": r.d,
                    "sigma_d": r.sigma_d,
                    "jersey": None,
                }
                for r in f.runners
            ],
        }
        for f in feats
    ]
    group = [{"x": 200 + 6.6 * (f.t - 10.0), "v": 6.6, "cut": False} for f in feats]
    resp = client.post("/api/athletes/", json={"t0": 0.0, "frames": frames, "group": group})
    assert resp.status_code == 200, resp.text
    data = resp.json()["frames"]
    assert len(data) == 30 and data[-1]["frame"] == 29
    assert {a["id"] for a in data[-1]["athletes"]} and all(
        a["visible"] for a in data[-1]["athletes"]
    )
    bad = client.post("/api/athletes/", json={"frames": frames, "group": group[:-1]})
    assert bad.status_code == 422
