"""Relato: la parte que no puede fallar es que no invente.

No toca la red: Claude y ElevenLabs se apagan con monkeypatch, así que se prueba el camino
determinista (hechos, validación, plantillas, caché) que es el que se ve cuando algo falla.
"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients.storage import LocalStorage
from app.core.config import settings
from app.cv.race_facts import allowed_numbers, build_facts
from app.dependencies.common import get_storage
from app.main import app
from app.schemas.athletes import AthletesResult
from app.schemas.narration import NarrationRequest, NarrationSegment
from app.schemas.tracking import TrackingResult
from app.schemas.zones import ZonesResult
from app.services.narration_service import NarrationService

FPS = 10
DURATION = 15.0


def _tracks() -> TrackingResult:
    """Clip sintético: dos corredores, uno se va a mitad de camino."""
    frames = []
    for i in range(int(DURATION * FPS)):
        t = round(i / FPS, 3)
        dets = [
            {"id": 4, "bbox": [100.0, 200.0, 160.0, 320.0], "foot_px": [130.0, 320.0], "conf": 0.9}
        ]
        if t < 8.0:
            dets.append(
                {
                    "id": 8,
                    "bbox": [300.0, 210.0, 360.0, 330.0],
                    "foot_px": [330.0, 330.0],
                    "conf": 0.8,
                }
            )
        frames.append({"frame": i, "t": t, "detections": dets})
    return TrackingResult.model_validate(
        {
            "video": {
                "source": "upload",
                "width": 1280,
                "height": 720,
                "fps_src": 60,
                "fps_out": FPS,
                "frames": len(frames),
                "duration_s": DURATION,
            },
            "pipeline": {
                "detector": "rfdetr-medium",
                "tracker": "bytetrack",
                "min_det_conf": 0.2,
                "min_on_track": 0.2,
                "min_track_on_track": 0.65,
            },
            "tracks": [
                {
                    "id": 4,
                    "t_start": 0.0,
                    "t_end": DURATION,
                    "n_obs": len(frames),
                    "on_track": 0.95,
                },
                {"id": 8, "t_start": 0.0, "t_end": 8.0, "n_obs": 80, "on_track": 0.9},
            ],
            "frames": frames,
        }
    )


def _zones() -> ZonesResult:
    frames = []
    for i in range(int(DURATION * FPS)):
        t = round(i / FPS, 3)
        zone = 2 if t < 3.5 else 3
        frames.append(
            {
                "frame": i,
                "t": t,
                "zone": zone,
                "p": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "s": round(100 + 6.7 * t, 1),
                "x": round(6.7 * t, 1),
                "x_std": 0.1,
                "v": 6.7,
                "cut": False,
                "recognized": False,
            }
        )
    return ZonesResult.model_validate(
        {
            "distance": 1500.0,
            "t0": 0.0,
            "zone_names": {
                "1": "curva 1 entrada",
                "2": "curva 1 salida",
                "3": "recta opuesta",
                "4": "curva 2 entrada",
                "5": "curva 2 salida",
                "6": "recta principal",
            },
            "cuts": [],
            "frames": frames,
        }
    )


def _athletes() -> AthletesResult:
    """Dos atletas: el #2 sale detrás y pasa al #1 hacia los 7 s; el #2 se abre por fuera."""
    frames = []
    for i in range(int(DURATION * FPS)):
        t = round(i / FPS, 3)
        passed = t >= 7.0
        x1 = 6.5 * t + 10
        x2 = 6.9 * t + 4
        rank1, rank2 = (2, 1) if passed else (1, 2)
        frames.append(
            {
                "frame": i,
                "t": t,
                "group": {"x": round(max(x1, x2), 1), "v": 6.7},
                "measured": True,
                "athletes": [
                    {
                        "id": 1,
                        "track_id": 4,
                        "rank": rank1,
                        "x": round(x1, 2),
                        "s": round((100 + x1) % 400, 2),
                        "d": 0.8,
                        "lane": 1,
                        "v": 6.5,
                        "u": -0.2,
                        "visible": True,
                        "sigma_x": 0.3,
                        "bbox": None,
                    },
                    {
                        "id": 2,
                        "track_id": 8,
                        "rank": rank2,
                        "x": round(x2, 2),
                        "s": round((100 + x2) % 400, 2),
                        "d": 4.0,
                        "lane": 3,
                        "v": 6.9,
                        "u": 0.2,
                        "visible": True,
                        "sigma_x": 0.3,
                        "bbox": None,
                    },
                ],
            }
        )
    return AthletesResult.model_validate({"t0": 0.0, "frames": frames})


def test_athlete_facts_have_speed_passes_and_extra_meters() -> None:
    facts = build_facts(_tracks(), _zones(), _athletes())
    athletes = facts["athletes"]

    assert "tracks" not in facts  # con atletas, los ids que se nombran son los de los atletas
    assert facts["runners"]["total"] == 2
    assert athletes["distance_m"] == 1500
    by_id = {r["id"]: r for r in athletes["runners"]}
    assert by_id[2]["max_kmh"] == pytest.approx(6.9 * 3.6, abs=0.1)
    assert by_id[2]["lane"] == 3 and by_id[1]["lane"] == 1
    # El que corre por fuera gasta metros de más en la curva; los de adentro, nada que informar.
    assert by_id[2]["extra_m"] >= 1.0
    assert by_id[1]["extra_m"] is None
    assert athletes["widest"]["id"] == 2
    assert [(p["id"], p["passes"]) for p in athletes["passes"]] == [(2, 1)]


def test_athletes_allow_positions_but_never_a_winner(service: NarrationService) -> None:
    facts = build_facts(_tracks(), _zones(), _athletes())
    windows = [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)]

    ok = _segments(
        windows,
        [
            "El #1 va primero del grupo.",
            "El #2 pasa al #1 y se abre por fuera.",
            "El #2 cierra la curva.",
        ],
    )
    assert service._validate(ok, windows, facts) is None

    wins = _segments(windows, ["El #1 va primero.", "El #2 pasa al #1.", "El #2 gana la carrera."])
    problem = service._validate(wins, windows, facts)
    assert problem is not None and "resultado" in problem

    # Sin atletas, hablar de puestos sigue vedado.
    plain = build_facts(_tracks(), _zones())
    problem = service._validate(
        _segments(windows, ["El #4 va primero.", "Sigue la toma.", "Cierra la toma."]),
        windows,
        plain,
    )
    assert problem is not None and "resultado" in problem


def test_template_with_athletes_stays_valid(service: NarrationService) -> None:
    facts = build_facts(_tracks(), _zones(), _athletes())
    windows = service._windows(DURATION, 5.0)
    segments = service._template_script(facts, windows)
    assert service._validate(segments, windows, facts) is None
    assert any("pasa al" in s.text for s in segments)


def test_the_prompt_asks_for_calm_and_football_voice() -> None:
    from app.services.narration_service import SYSTEM_PROMPT

    assert "fútbol" in SYSTEM_PROMPT
    assert "MAREAR" in SYSTEM_PROMPT
    assert "UN dato numérico por frase" in SYSTEM_PROMPT


def test_facts_summarize_instead_of_dumping_frames() -> None:
    facts = build_facts(_tracks(), _zones())

    assert facts["clip"]["duration_s"] == DURATION
    assert facts["runners"] == {"total": 2, "peak_on_screen": 2, "median_on_screen": 2}
    assert [t["id"] for t in facts["tracks"]] == [4, 8]
    assert facts["tracks"][1]["out_s"] == 8.0
    # La cámara: dos tramos, empieza en la salida de la curva 1.
    assert [s["zone_name"] for s in facts["camera"]["timeline"]] == [
        "curva 1 salida",
        "recta opuesta",
    ]
    assert facts["camera"]["span_m"] == pytest.approx(100)
    # Lo que no se puede afirmar viaja en los hechos, no solo en el prompt.
    assert "posiciones o puestos de cada corredor" in facts["cannot_claim"]


def test_facts_omit_camera_without_zones() -> None:
    assert "camera" not in build_facts(_tracks(), None)


def test_allowed_numbers_come_from_the_facts() -> None:
    allowed = allowed_numbers(build_facts(_tracks(), _zones()))
    assert 15.0 in allowed  # duración
    assert 6.7 in allowed  # barrido
    assert 101 in allowed or 100 in allowed  # tramo


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> NarrationService:
    # Sin credenciales: se prueba el camino que corre cuando todo lo externo falla.
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "eleven_labs_api_key", "")
    return NarrationService(LocalStorage(tmp_path))


def _segments(spans: list[tuple[float, float]], texts: list[str]) -> list[NarrationSegment]:
    return [
        NarrationSegment(start=s, end=e, text=t) for (s, e), t in zip(spans, texts, strict=True)
    ]


def test_validation_accepts_a_faithful_script(service: NarrationService) -> None:
    facts = build_facts(_tracks(), _zones())
    windows = [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)]
    ok = _segments(
        windows,
        [
            "Arranca con dos corredores en cuadro.",
            "La cámara recorre cien metros por la recta opuesta.",
            "El seguimiento confirma dos atletas.",
        ],
    )
    assert service._validate(ok, windows, facts) is None


@pytest.mark.parametrize(
    ("spans", "texts", "expected"),
    [
        # Afirma un resultado que el sistema no mide.
        (
            [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)],
            ["El #4 gana la carrera.", "La cámara avanza.", "El seguimiento sigue."],
            "resultado",
        ),
        # Cifra que no está en los hechos.
        (
            [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)],
            ["Nueve corredores en cuadro.", "La cámara recorre 87 metros.", "Cierra la toma."],
            "cifra",
        ),
        # Hueco en la cobertura del clip.
        (
            [(0.0, 3.0), (5.0, 10.0), (10.0, 15.0)],
            ["Arranca el clip con corredores.", "Sigue la toma.", "Cierra la toma."],
            "hueco",
        ),
    ],
)
def test_validation_rejects_what_we_cannot_support(
    service: NarrationService,
    spans: list[tuple[float, float]],
    texts: list[str],
    expected: str,
) -> None:
    facts = build_facts(_tracks(), _zones())
    problem = service._validate(
        _segments(spans, texts), [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)], facts
    )
    assert problem is not None and expected in problem


def test_template_script_covers_the_whole_clip(service: NarrationService) -> None:
    facts = build_facts(_tracks(), _zones())
    windows = service._windows(DURATION, 5.0)
    segments = service._template_script(facts, windows)

    assert windows == [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)]
    assert [s.start for s in segments] == [0.0, 5.0, 10.0]
    assert segments[-1].end == 15.0
    assert service._validate(segments, windows, facts) is None


def test_narrate_falls_back_to_template_and_caches(service: NarrationService) -> None:
    request = NarrationRequest(tracks=_tracks(), zones=_zones(), segment_s=5.0)

    first = asyncio.run(service.narrate(request))
    second = asyncio.run(service.narrate(request))

    assert first.source == "template"
    assert first.cached is False and second.cached is True
    assert second.key == first.key
    assert first.audio == []  # sin ElevenLabs queda solo el texto
    assert first.characters == 0
    assert len(first.segments) == 3
    assert all(seg.text for seg in first.segments)


def test_endpoint_returns_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "eleven_labs_api_key", "")
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/narration/",
                json={"tracks": _tracks().model_dump(), "zones": _zones().model_dump()},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "template"
    assert body["disclaimer"]
    # Por defecto son tramos de ~8 s: dos para un clip de 15 s.
    assert [s["start"] for s in body["segments"]] == [0.0, 7.5]
    assert body["segments"][-1]["end"] == DURATION
    assert body["audio"] == []
