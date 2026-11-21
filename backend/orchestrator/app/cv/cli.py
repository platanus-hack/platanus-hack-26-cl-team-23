"""Uso: uv run python -m app.cv.cli --source app/assets/NCCA.mp4

Genera <out>/<video>.tracks.json y <out>/<video>.tracked.mp4. Las detecciones se
cachean en <out>/<video>.detections.json: re-ejecutar no vuelve a llamar a Roboflow.
"""

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.core.logger import logger
from app.cv.annotate import render_video
from app.cv.detector import RoboflowDetector
from app.cv.pipeline import (
    TrackingParams,
    detect_video,
    read_meta,
    score_on_track,
    track,
)


def _load_cache(cache_file: Path, key: dict) -> dict | None:
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached.get("key") == key:
            return cached
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Detección + ByteTrack sobre un video")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("app/assets/out"))
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--no-cache", action="store_true", help="Volver a llamar a Roboflow")
    parser.add_argument("--no-video", action="store_true", help="Solo JSON, sin MP4 anotado")
    args = parser.parse_args()

    detector = RoboflowDetector(
        api_key=settings.roboflow_api_key,
        api_url=settings.roboflow_api_url,
        model_id=settings.roboflow_model_id,
    )
    params = TrackingParams(fps_out=args.fps)
    args.out.mkdir(parents=True, exist_ok=True)

    meta = read_meta(args.source)
    cache_file = args.out / f"{args.source.stem}.detections.json"
    key = {"model": detector.model_id, "fps_out": args.fps, "duration_s": round(meta.duration_s, 3)}
    cached = None if args.no_cache else _load_cache(cache_file, key)

    if cached:
        logger.info("Detecciones desde caché: %s", cache_file)
        indices, raw = cached["indices"], cached["detections"]
    else:
        _, indices, raw = detect_video(
            args.source,
            detector,
            args.fps,
            on_progress=lambda done, total: logger.info("  %d/%d frames", done, total),
        )
        cache_file.write_text(json.dumps({"key": key, "indices": indices, "detections": raw}))

    scored = score_on_track(args.source, indices, raw)
    times = [i / meta.fps_src for i in indices]
    result = track(meta, indices, times, scored, params, model_id=detector.model_id)

    json_path = args.out / f"{args.source.stem}.tracks.json"
    json_path.write_text(json.dumps(result, separators=(",", ":")))
    logger.info(
        "tracks.json: %s (%.0f KB) | %d tracks, %d frames",
        json_path,
        json_path.stat().st_size / 1024,
        len(result["tracks"]),
        len(result["frames"]),
    )
    for t in result["tracks"]:
        logger.info(
            "  id=%-3d %.1fs -> %.1fs (%d obs)", t["id"], t["t_start"], t["t_end"], t["n_obs"]
        )

    if not args.no_video:
        video_path = render_video(args.source, result, args.out / f"{args.source.stem}.tracked.mp4")
        logger.info("MP4 anotado: %s", video_path)


if __name__ == "__main__":
    main()
