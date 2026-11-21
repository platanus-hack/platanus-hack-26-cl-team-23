from app.cv.pipeline import TrackingParams, VideoMeta, track

META = VideoMeta(source="synthetic.mp4", width=1280, height=720, fps_src=60.0, duration_s=10.0)
ROI = [(0, 200), (1280, 200), (1280, 500), (0, 500)]


def _frames(n: int) -> tuple[list[int], list[list[list[float]]]]:
    indices = list(range(0, n * 4, 4))
    raw = []
    for i in range(n):
        runner_a = [100 + 6 * i, 300, 140 + 6 * i, 380, 0.9, 0.95]
        runner_b = [300 + 5 * i, 320, 340 + 5 * i, 400, 0.85, 0.9]
        crowd = [500, 20, 540, 100, 0.8, 0.0]  # sin pista bajo los pies (tribuna)
        raw.append([runner_a, runner_b, crowd])
    return indices, raw


def test_track_keeps_stable_ids_and_filters_crowd() -> None:
    indices, raw = _frames(60)
    times = [i / META.fps_src for i in indices]
    result = track(META, indices, times, raw, TrackingParams(roi=ROI))

    assert len(result["tracks"]) == 2
    assert {t["id"] for t in result["tracks"]} == {
        d["id"] for d in result["frames"][-1]["detections"]
    }
    last = result["frames"][-1]
    assert all(d["foot_px"][1] == d["bbox"][3] for d in last["detections"])


def test_track_timestamps_are_seconds_of_source_video() -> None:
    indices, raw = _frames(10)
    times = [i / META.fps_src for i in indices]
    result = track(META, indices, times, raw, TrackingParams(roi=ROI, min_track_seconds=0))

    assert result["frames"][1]["t"] == round(4 / 60.0, 3)
    assert result["video"]["fps_out"] == 15.0
