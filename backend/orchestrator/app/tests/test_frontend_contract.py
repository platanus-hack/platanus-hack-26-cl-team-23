"""Contrato con el SPA: la cadena exacta que corre el navegador al subir un video.

El front saca cuadros, los manda en lotes a /analyze (equivale a /detect y /zones/features
sobre los MISMOS archivos), y después cierra con una llamada a /track y otra a /zones/. El
adaptador une ambos resultados por el número de cuadro, así que eso es lo que se verifica aquí.
"""

from collections.abc import Iterator

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.dependencies.common import get_detector_provider
from app.main import app

SAMPLE_FPS = 10  # el mismo de frontend/spa/src/trazada/upload.ts
BATCH = 24  # MAX_BATCH_FRAMES
FRAMES = 30  # dos lotes, como un video corto de verdad


class FakeDetector:
    """Un corredor que cruza el cuadro: suficiente para que ByteTrack le dé un id."""

    model_id = "fake-model"

    def __init__(self, frame_index: int = 0) -> None:
        self._i = frame_index

    def detect_many(self, frames: list[np.ndarray], on_progress: object = None) -> list:
        out = []
        for _ in frames:
            x = 40 + 4 * self._i
            out.append([[x, 90, x + 20, 140, 0.9]])
            self._i += 1
        return out


def _jpeg(width: int = 320, height: int = 180) -> bytes:
    frame = np.full((height, width, 3), 200, dtype=np.uint8)
    frame[height // 2 :] = (40, 40, 170)  # mitad inferior color pista -> on_track alto
    cv2.line(frame, (0, height - 20), (width, height - 40), (255, 255, 255), 2)
    ok, buffer = cv2.imencode(".jpg", frame)
    assert ok
    return buffer.tobytes()


def _batch(start: int, size: int) -> dict:
    """Lo mismo que arma el FormData del navegador."""
    return {
        "files": [("frames", (f"f{start + i}.jpg", _jpeg(), "image/jpeg")) for i in range(size)],
        "data": {
            "t": [round((start + i) / SAMPLE_FPS, 4) for i in range(size)],
            "orig_width": 1280,
            "orig_height": 720,
        },
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    detector = FakeDetector()
    app.dependency_overrides[get_detector_provider] = lambda: lambda: detector
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_detect_then_track_matches_spa_flow(client: TestClient) -> None:
    detected: list[dict] = []
    for start in range(0, FRAMES, BATCH):
        batch = _batch(start, min(BATCH, FRAMES - start))
        response = client.post("/api/tracking/detect", **batch)
        assert response.status_code == 200, response.text
        detected += response.json()["frames"]

    assert len(detected) == FRAMES
    assert [f["t"] for f in detected] == sorted(f["t"] for f in detected)

    tracked = client.post(
        "/api/tracking/track",
        json={
            "source": "upload",
            "width": 1280,
            "height": 720,
            "fps_out": SAMPLE_FPS,
            "frames": [{"t": f["t"], "dets": f["dets"]} for f in detected],
        },
    )

    assert tracked.status_code == 200, tracked.text
    body = tracked.json()
    # El adaptador asume un cuadro de salida por cada cuadro enviado, numerados desde 0.
    assert [f["frame"] for f in body["frames"]] == list(range(FRAMES))
    assert body["video"]["duration_s"] == pytest.approx((FRAMES - 1) / SAMPLE_FPS, abs=1e-3)
    assert len(body["tracks"]) == 1
    detection = body["frames"][-1]["detections"][0]
    assert detection["id"] == body["tracks"][0]["id"]
    # foot_px es el centro de la base de la caja: ahí es donde pisa.
    x1, _, x2, y2 = detection["bbox"]
    assert detection["foot_px"] == [pytest.approx((x1 + x2) / 2), y2]


def test_zone_features_then_zones_share_the_frame_index(client: TestClient) -> None:
    features: list[dict] = []
    for start in range(0, FRAMES, BATCH):
        batch = _batch(start, min(BATCH, FRAMES - start))
        response = client.post(
            "/api/zones/features", files=batch["files"], data={"t": batch["data"]["t"]}
        )
        assert response.status_code == 200, response.text
        features += response.json()["frames"]

    assert len(features) == FRAMES

    # El front manda `desc` solo cada ~0,5 s; `hist` en todos los cuadros.
    payload = [
        {"t": f["t"], "hist": f["hist"], **({"desc": f["desc"]} if i % 5 == 0 else {})}
        for i, f in enumerate(features)
    ]
    zones = client.post(
        "/api/zones/", json={"source": "upload", "distance": 1500, "t0": 0, "frames": payload}
    )

    assert zones.status_code == 200, zones.text
    body = zones.json()
    # Mismo índice que /track: por ahí los une el adaptador.
    assert [f["frame"] for f in body["frames"]] == list(range(FRAMES))
    assert [f["t"] for f in body["frames"]] == [f["t"] for f in features]
    assert all(1 <= f["zone"] <= 6 for f in body["frames"])
    assert set(body["zone_names"]) == {"1", "2", "3", "4", "5", "6"}


def test_analyze_equals_detect_plus_zone_features(client: TestClient) -> None:
    """Una sola subida debe dar lo mismo que /detect y /zones/features por separado."""
    batch = _batch(0, 6)
    zone_files = batch["files"]

    separate_detect = client.post("/api/tracking/detect", **batch)
    separate_zones = client.post(
        "/api/zones/features", files=zone_files, data={"t": batch["data"]["t"]}
    )
    assert separate_detect.status_code == 200, separate_detect.text
    assert separate_zones.status_code == 200, separate_zones.text

    client.app.dependency_overrides[get_detector_provider] = lambda: lambda: FakeDetector()
    both = client.post("/api/tracking/analyze", **batch)

    assert both.status_code == 200, both.text
    body = both.json()
    assert body["detect"] == separate_detect.json()
    assert body["zones"] == separate_zones.json()


def test_want_desc_skips_appearance_but_keeps_values_where_asked(client: TestClient) -> None:
    """Los cuadros sin bandera solo traen `hist`; los marcados traen lo mismo que sin bandera."""
    batch = _batch(0, 10)
    full = client.post("/api/zones/features", files=batch["files"], data={"t": batch["data"]["t"]})
    flags = [i % 5 == 0 for i in range(10)]
    partial = client.post(
        "/api/zones/features",
        files=batch["files"],
        data={"t": batch["data"]["t"], "want_desc": flags},
    )

    assert full.status_code == 200, full.text
    assert partial.status_code == 200, partial.text
    for i, (a, b) in enumerate(zip(full.json()["frames"], partial.json()["frames"], strict=True)):
        assert b["hist"] == a["hist"]
        if flags[i]:
            assert b == a
        else:
            assert (b["desc"], b["bend"], b["chord"], b["n"]) == (None, None, None, None)


def test_want_desc_must_match_frame_count(client: TestClient) -> None:
    batch = _batch(0, 3)
    response = client.post(
        "/api/zones/features",
        files=batch["files"],
        data={"t": batch["data"]["t"], "want_desc": [True]},
    )
    assert response.status_code == 422, response.text


def test_analyze_without_zones_skips_them(client: TestClient) -> None:
    batch = _batch(0, 3)
    batch["data"]["with_zones"] = False

    response = client.post("/api/tracking/analyze", **batch)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["detect"]["frames"]) == 3
    assert body["zones"] is None


def test_analyze_keeps_tracking_when_zones_fail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.zones_service import ZonesService

    async def boom(
        self: ZonesService,
        images: list[bytes],
        times: list[float],
        want_desc: list[bool] | None = None,
    ) -> None:
        raise RuntimeError("sin evidencia")

    monkeypatch.setattr(ZonesService, "features", boom)

    response = client.post("/api/tracking/analyze", **_batch(0, 3))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["detect"]["frames"]) == 3
    assert body["zones"] is None
