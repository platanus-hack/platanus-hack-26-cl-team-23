import shutil
import subprocess
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np

from app.core.logger import logger

TRAIL_LENGTH = 40


def _color(track_id: int) -> tuple[int, int, int]:
    hue = (track_id * 47) % 180
    bgr = cv2.cvtColor(np.uint8([[[hue, 220, 255]]]), cv2.COLOR_HSV2BGR)[0][0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


def render_video(video_path: Path, result: dict, out_path: Path) -> Path:
    """Dibuja cajas, IDs y estela de los pies sobre el video original, a fps_out."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = result["video"]
    by_frame = {f["frame"]: f for f in result["frames"]}
    roi = result["pipeline"].get("roi")

    raw_path = out_path.with_suffix(".raw.mp4")
    writer = cv2.VideoWriter(
        str(raw_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        meta["fps_out"],
        (meta["width"], meta["height"]),
    )
    trails: dict[int, deque] = defaultdict(lambda: deque(maxlen=TRAIL_LENGTH))

    cap = cv2.VideoCapture(str(video_path))
    idx = 0
    while cap.grab():
        if idx in by_frame:
            ok, frame = cap.retrieve()
            if ok:
                if roi:
                    cv2.polylines(frame, [np.array(roi, dtype=np.int32)], True, (255, 255, 0), 1)
                visible = {d["id"] for d in by_frame[idx]["detections"]}
                for stale in [tid for tid in trails if tid not in visible]:
                    del trails[stale]
                for d in by_frame[idx]["detections"]:
                    color = _color(d["id"])
                    x1, y1, x2, y2 = (int(v) for v in d["bbox"])
                    trails[d["id"]].append(tuple(int(v) for v in d["foot_px"]))
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        frame,
                        f"#{d['id']}",
                        (x1, max(14, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        color,
                        2,
                    )
                for tid, pts in trails.items():
                    if len(pts) > 1:
                        cv2.polylines(frame, [np.array(pts, dtype=np.int32)], False, _color(tid), 2)
                writer.write(frame)
        idx += 1
    cap.release()
    writer.release()

    if shutil.which("ffmpeg"):
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_path),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(out_path),
            ],
            check=True,
        )  # fmt: skip
        raw_path.unlink()
    else:
        logger.warning("ffmpeg no encontrado: el MP4 usa mp4v y no se verá en navegadores")
        raw_path.replace(out_path)
    return out_path
