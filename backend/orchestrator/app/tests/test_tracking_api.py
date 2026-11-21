from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.clients.storage import LocalStorage
from app.core.config import settings
from app.cv.detector import DetectorError
from app.dependencies.common import get_detector_provider, get_storage
from app.main import app


class FakeDetector:
    model_id = "fake-model"

    def __init__(self, box: list[float] | None = None) -> None:
        self._box = box

    def detect_many(self, frames: Iterable[np.ndarray], on_progress: object = None) -> list:
        return [[self._box] if self._box else [] for _ in frames]


def _jpeg(width: int = 320, height: int = 180) -> bytes:
    """Frame sintético: mitad inferior color pista (rojo) para que on_track sea alto."""
    frame = np.full((height, width, 3), 200, dtype=np.uint8)
    frame[height // 2 :] = (40, 40, 170)
    ok, buffer = cv2.imencode(".jpg", frame)
    assert ok
    return buffer.tobytes()


def _write_preset_video(path: Path, seconds: int = 2, fps: int = 15) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 180))
    frame = cv2.imdecode(np.frombuffer(_jpeg(), np.uint8), cv2.IMREAD_COLOR)
    for _ in range(seconds * fps):
        writer.write(frame)
    writer.release()
    assert path.stat().st_size > 0


@pytest.fixture
def override(tmp_path: Path) -> Iterator[Callable[[FakeDetector | Exception], TestClient]]:
    clients: list[TestClient] = []

    def make(detector: FakeDetector | Exception) -> TestClient:
        def provider() -> object:
            if isinstance(detector, Exception):
                raise detector
            return detector

        _write_preset_video(tmp_path / "presets" / "NCCA.mp4")
        app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
        app.dependency_overrides[get_detector_provider] = lambda: provider
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    app.dependency_overrides.clear()


def test_detect_returns_boxes_in_original_resolution(override) -> None:
    client = override(FakeDetector([10, 20, 50, 150, 0.9]))
    response = client.post(
        "/api/tracking/detect",
        files=[
            ("frames", ("a.jpg", _jpeg(), "image/jpeg")),
            ("frames", ("b.jpg", _jpeg(), "image/jpeg")),
        ],
        data={"t": [0.0, 0.0667], "orig_width": 1280, "orig_height": 720},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model"] == "fake-model"
    assert [f["t"] for f in body["frames"]] == [0.0, 0.0667]
    x1, y1, x2, y2, conf, on_track = body["frames"][0]["dets"][0]
    assert (x1, y1, x2, y2) == (40.0, 80.0, 200.0, 600.0)  # escala 4x
    assert conf == 0.9
    assert on_track > 0.8


def test_detect_validates_input(override) -> None:
    client = override(FakeDetector())
    mismatch = client.post(
        "/api/tracking/detect",
        files=[("frames", ("a.jpg", _jpeg(), "image/jpeg"))],
        data={"t": [0.0, 1.0], "orig_width": 1280, "orig_height": 720},
    )
    garbage = client.post(
        "/api/tracking/detect",
        files=[("frames", ("a.jpg", b"no soy una imagen", "image/jpeg"))],
        data={"t": [0.0], "orig_width": 1280, "orig_height": 720},
    )

    assert mismatch.status_code == 422
    assert garbage.status_code == 422


def test_detect_reports_missing_api_key_as_502(override) -> None:
    client = override(DetectorError("ROBOFLOW_API_KEY está vacío"))
    response = client.post(
        "/api/tracking/detect",
        files=[("frames", ("a.jpg", _jpeg(), "image/jpeg"))],
        data={"t": [0.0], "orig_width": 1280, "orig_height": 720},
    )

    assert response.status_code == 502


def test_demo_key_protects_spending_endpoints(override, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_access_key", "secreto")
    client = override(FakeDetector([10, 20, 50, 150, 0.9]))
    request = {
        "files": [("frames", ("a.jpg", _jpeg(), "image/jpeg"))],
        "data": {"t": [0.0], "orig_width": 320, "orig_height": 180},
    }

    assert client.post("/api/tracking/detect", **request).status_code == 401
    assert (
        client.post("/api/tracking/detect", **request, headers={"X-Demo-Key": "mal"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/tracking/detect", **request, headers={"X-Demo-Key": "secreto"}
        ).status_code
        == 200
    )
    assert client.post("/api/tracking/process", json={"source": "NCCA"}).status_code == 401


def test_track_builds_stable_ids_from_client_detections(override) -> None:
    client = override(FakeDetector())
    frames = [
        {
            "t": round(i / 15, 4),
            "dets": [
                [100 + 6 * i, 300, 140 + 6 * i, 380, 0.9, 0.95],
                [300 + 5 * i, 320, 340 + 5 * i, 400, 0.85, 0.9],
            ],
        }
        for i in range(45)
    ]
    response = client.post(
        "/api/tracking/track",
        json={"source": "juez.mp4", "width": 1280, "height": 720, "fps_out": 15, "frames": frames},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["tracks"]) == 2
    assert body["video"]["source"] == "juez.mp4"
    assert len(body["frames"]) == 45
    assert body["frames"][-1]["t"] == round(44 / 15, 3)


def test_track_rejects_non_increasing_time(override) -> None:
    client = override(FakeDetector())
    frames = [{"t": 0.5, "dets": []}, {"t": 0.5, "dets": []}]
    response = client.post(
        "/api/tracking/track",
        json={"width": 1280, "height": 720, "frames": frames},
    )

    assert response.status_code == 422


def test_process_runs_pipeline_then_serves_from_cache(override) -> None:
    client = override(FakeDetector())

    first = client.post("/api/tracking/process", json={"source": "NCCA"})
    second = client.post("/api/tracking/process", json={"source": "NCCA"})

    assert first.status_code == 200, first.text
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["key"] == first.json()["key"]
    stored = client.get(f"/api/tracking/results/{first.json()['key']}")
    assert stored.status_code == 200
    assert stored.json()["video"]["source"] == "NCCA.mp4"


def test_process_reports_missing_preset_video(override, tmp_path: Path) -> None:
    client = override(FakeDetector())
    (tmp_path / "presets" / "NCCA.mp4").unlink()

    assert client.post("/api/tracking/process", json={"source": "NCCA"}).status_code == 404


def test_process_requires_exactly_one_source(override) -> None:
    client = override(FakeDetector())

    assert client.post("/api/tracking/process", json={}).status_code == 422
    both = client.post("/api/tracking/process", json={"source": "NCCA", "blob": "videos/x.mp4"})
    assert both.status_code == 422
    assert client.post("/api/tracking/process", json={"source": "NOPE"}).status_code == 404
    assert client.post("/api/tracking/process", json={"blob": "otra/x.mp4"}).status_code == 422
    assert (
        client.post("/api/tracking/process", json={"blob": "videos/no-existe.mp4"}).status_code
        == 404
    )


def test_preset_and_results_lookup(override, tmp_path: Path) -> None:
    client = override(FakeDetector())

    assert client.get("/api/tracking/presets/NCCA").status_code == 404  # aún no publicado
    tracked = client.post(
        "/api/tracking/track",
        json={
            "source": "NCCA.mp4",
            "width": 320,
            "height": 180,
            "frames": [{"t": 0.0, "dets": []}],
        },
    )
    assert tracked.status_code == 200, tracked.text
    (tmp_path / "presets" / "NCCA.tracks.json").write_bytes(tracked.content)

    preset = client.get("/api/tracking/presets/NCCA")
    assert preset.status_code == 200
    assert preset.json()["video"]["source"] == "NCCA.mp4"
    assert client.get("/api/tracking/presets/NOPE").status_code == 404
    assert client.get("/api/tracking/results/no-existe").status_code == 404
    assert client.get("/api/tracking/results/..%2Fsecreto").status_code in {404, 422}
