import itertools

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.cv.zones import pipeline
from app.cv.zones.evidence import DESC_SIZE, HIST_SIZE, CutDetector
from app.cv.zones.layout import start_s, zone_edges, zone_of
from app.cv.zones.track import STANDARD


def _jpeg(color: tuple[int, int, int], width: int = 320, height: int = 180) -> bytes:
    frame = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", frame)
    assert ok
    return buffer.tobytes()


def _feature(t: float, hist_seed: int = 0, with_desc: bool = True) -> dict:
    rng = np.random.default_rng(hist_seed)
    hist = rng.random(HIST_SIZE)
    hist /= np.linalg.norm(hist)
    return {
        "t": t,
        "hist": hist.tolist(),
        "desc": rng.random(DESC_SIZE).tolist() if with_desc else None,
        "bend": 0.004,
        "chord": 900.0,
        "n": 3,
    }


def test_zone_layout() -> None:
    edges = zone_edges()
    assert len(edges) == 7 and edges[0] == 0 and abs(edges[-1] - STANDARD.lap) < 1e-9
    assert zone_of(0.0) == 1 and zone_of(399.9) == 6 and zone_of(-1.0) == 6
    assert abs(start_s(1500) - 100.0) < 0.01 and zone_of(start_s(1500)) == 2


def test_cut_detector_flags_scene_change_only() -> None:
    a, b = np.zeros(HIST_SIZE), np.zeros(HIST_SIZE)
    a[:10], b[100:110] = 1.0, 1.0
    detector = CutDetector()
    assert [detector(h, t) for h, t in [(a, 0.0), (a, 0.1), (b, 0.2), (b, 0.3)]] == [
        False,
        False,
        True,
        False,
    ]


def test_pipeline_leader_advances_through_zones_in_order() -> None:
    feats = [
        pipeline.FrameFeatures(
            t=0.1 * i + 5.0, hist=np.asarray(_feature(0, 1)["hist"], dtype=np.float32)
        )
        for i in range(1800)
    ]
    out = pipeline.run(feats, pipeline.ZoneParams(distance=1500, t0=5.0))
    zones = [f["zone"] for f in out.frames]
    assert zones[0] == 2  # el 1500 parte en Z2
    assert all(1 <= z <= 6 for z in zones)
    assert [z for z, _ in itertools.groupby(zones)][:4] == [2, 3, 4, 5]
    assert out.frames[-1]["x"] > 1000


def test_pipeline_is_deterministic() -> None:
    feats = [
        pipeline.FrameFeatures(t=0.2 * i, hist=np.asarray(_feature(0, 1)["hist"], dtype=np.float32))
        for i in range(100)
    ]
    a = pipeline.run(feats, pipeline.ZoneParams(seed=3))
    b = pipeline.run(feats, pipeline.ZoneParams(seed=3))
    assert a.frames == b.frames


def test_features_endpoint(client: TestClient) -> None:
    files = [("frames", ("a.jpg", _jpeg((40, 40, 170)), "image/jpeg")) for _ in range(2)]
    resp = client.post("/api/zones/features", files=files, data={"t": [0.0, 0.1]})
    assert resp.status_code == 200, resp.text
    frames = resp.json()["frames"]
    assert len(frames) == 2
    assert len(frames[0]["hist"]) == HIST_SIZE and len(frames[0]["desc"]) == DESC_SIZE


def test_features_rejects_mismatched_times(client: TestClient) -> None:
    files = [("frames", ("a.jpg", _jpeg((0, 0, 0)), "image/jpeg"))]
    resp = client.post("/api/zones/features", files=files, data={"t": [0.0, 0.1]})
    assert resp.status_code == 422


def test_zones_endpoint(client: TestClient) -> None:
    body = {
        "distance": 1500,
        "t0": 1.0,
        "frames": [_feature(0.5 * i, 7, with_desc=i % 2 == 0) for i in range(40)],
    }
    resp = client.post("/api/zones/", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["frames"]) == 40
    assert data["frames"][0]["frame"] == 0 and data["frames"][-1]["frame"] == 39
    assert set(data["zone_names"]) == {"1", "2", "3", "4", "5", "6"}
    assert all(len(f["p"]) == 6 and 1 <= f["zone"] <= 6 for f in data["frames"])


def test_zones_requires_increasing_time(client: TestClient) -> None:
    body = {"frames": [_feature(1.0), _feature(1.0)]}
    assert client.post("/api/zones/", json=body).status_code == 422


def test_zones_validates_feature_sizes(client: TestClient) -> None:
    bad = _feature(0.0)
    bad["hist"] = [0.1] * 5
    assert client.post("/api/zones/", json={"frames": [bad]}).status_code == 422
