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
from app.cv.pipeline import TrackingParams, detect_video, track


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

    meta, indices, raw = detect_video(
        args.source, detector, args.fps, cache_dir=args.out, use_cache=not args.no_cache
    )
    result = track(meta, indices, raw, params, model_id=detector.model_id)

    args.out.mkdir(parents=True, exist_ok=True)
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
