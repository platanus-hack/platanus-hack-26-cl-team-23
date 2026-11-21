import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import supervision as sv
from trackers import ByteTrackTracker

from app.core.logger import logger
from app.cv.detector import RoboflowDetector
from app.cv.surface import on_track_fraction, to_hsv

Point = tuple[float, float]


@dataclass
class TrackingParams:
    fps_out: float = 15.0
    min_det_conf: float = 0.2
    min_on_track: float = 0.35
    min_track_on_track: float = 0.65
    roi: list[Point] | None = None
    lost_track_buffer: int = 30
    track_activation_threshold: float = 0.6
    minimum_consecutive_frames: int = 3
    minimum_iou_threshold: float = 0.1
    high_conf_det_threshold: float = 0.5
    min_track_seconds: float = 1.0


@dataclass
class VideoMeta:
    source: str
    width: int
    height: int
    fps_src: float
    frames_src: int

    @property
    def duration_s(self) -> float:
        return self.frames_src / self.fps_src


def read_meta(video_path: Path) -> VideoMeta:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"No se pudo abrir el video: {video_path}")
    meta = VideoMeta(
        source=video_path.name,
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        fps_src=cap.get(cv2.CAP_PROP_FPS),
        frames_src=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    )
    cap.release()
    return meta


def sample_indices(meta: VideoMeta, fps_out: float) -> list[int]:
    stride = max(1, round(meta.fps_src / fps_out))
    return list(range(0, meta.frames_src, stride))


def iter_frames(
    video_path: Path, indices: list[int], read_indices: list[int]
) -> Iterator[np.ndarray]:
    """Entrega los frames pedidos; registra en read_indices los que se pudieron decodificar.

    El conteo de frames del header puede sobreestimar los reales, por eso no se asume.
    """
    wanted = set(indices)
    cap = cv2.VideoCapture(str(video_path))
    try:
        idx = 0
        while cap.grab():
            if idx in wanted:
                ok, frame = cap.retrieve()
                if ok:
                    read_indices.append(idx)
                    yield frame
            idx += 1
    finally:
        cap.release()


def score_on_track(
    video_path: Path, indices: list[int], detections: list[list[list[float]]]
) -> list[list[list[float]]]:
    """Agrega a cada detección la fracción de pista bajo sus pies: [x1,y1,x2,y2,conf,on_track].

    Pasada local sobre el video (sin llamadas a la API), por eso no se cachea.
    """
    scored: list[list[list[float]]] = []
    for frame, dets in zip(iter_frames(video_path, indices, []), detections, strict=True):
        hsv = to_hsv(frame)
        scored.append([[*d[:5], round(on_track_fraction(hsv, d), 3)] for d in dets])
    return scored


def detect_video(
    video_path: Path,
    detector: RoboflowDetector,
    fps_out: float,
    cache_dir: Path | None = None,
    use_cache: bool = True,
) -> tuple[VideoMeta, list[int], list[list[list[float]]]]:
    """Detecta personas en los frames muestreados. Cachea en disco para no gastar créditos."""
    meta = read_meta(video_path)
    wanted = sample_indices(meta, fps_out)
    cache_file = cache_dir / f"{video_path.stem}.detections.json" if cache_dir else None
    cache_key = {"model": detector.model_id, "fps_out": fps_out, "source_frames": meta.frames_src}

    if use_cache and cache_file and cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached.get("key") == cache_key:
            logger.info("Detecciones desde caché: %s", cache_file)
            return (
                meta,
                cached["indices"],
                score_on_track(video_path, cached["indices"], cached["detections"]),
            )

    logger.info("Detectando ~%d frames de %s ...", len(wanted), video_path.name)
    read_indices: list[int] = []
    detections = detector.detect_many(
        iter_frames(video_path, wanted, read_indices),
        on_progress=lambda n: logger.info("  %d/%d frames", n, len(wanted)),
    )
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"key": cache_key, "indices": read_indices, "detections": detections})
        )
    return meta, read_indices, score_on_track(video_path, read_indices, detections)


def _in_roi(roi: np.ndarray | None, point: Point) -> bool:
    if roi is None:
        return True
    return cv2.pointPolygonTest(roi, point, False) >= 0


def _on_track_of(box: np.ndarray, candidates: np.ndarray) -> float:
    """on_track de la detección que mejor solapa con la caja (la del tracker es de Kalman)."""
    if len(candidates) == 0:
        return 0.0
    x1 = np.maximum(box[0], candidates[:, 0])
    y1 = np.maximum(box[1], candidates[:, 1])
    x2 = np.minimum(box[2], candidates[:, 2])
    y2 = np.minimum(box[3], candidates[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (box[2] - box[0]) * (box[3] - box[1])
    area_b = (candidates[:, 2] - candidates[:, 0]) * (candidates[:, 3] - candidates[:, 1])
    iou = inter / np.maximum(area_a + area_b - inter, 1e-6)
    return float(candidates[int(np.argmax(iou)), 5])


def track(
    meta: VideoMeta,
    indices: list[int],
    raw_detections: list[list[list[float]]],
    params: TrackingParams,
    model_id: str = "",
) -> dict:
    """Aplica ROI + ByteTrack sobre detecciones crudas y arma el JSON del contrato."""
    roi = np.array(params.roi, dtype=np.int32) if params.roi else None
    tracker = ByteTrackTracker(
        lost_track_buffer=params.lost_track_buffer,
        frame_rate=params.fps_out,
        track_activation_threshold=params.track_activation_threshold,
        minimum_consecutive_frames=params.minimum_consecutive_frames,
        minimum_iou_threshold=params.minimum_iou_threshold,
        high_conf_det_threshold=params.high_conf_det_threshold,
    )

    frames_out: list[dict] = []
    spans: dict[int, dict] = {}

    for idx, dets in zip(indices, raw_detections, strict=True):
        t = round(idx / meta.fps_src, 3)
        kept = [
            d
            for d in dets
            if d[4] >= params.min_det_conf
            and d[5] >= params.min_on_track
            and _in_roi(roi, ((d[0] + d[2]) / 2, d[3]))
        ]
        arr = np.array(kept, dtype=np.float32).reshape(-1, 6)
        detections = sv.Detections(
            xyxy=arr[:, :4],
            confidence=arr[:, 4],
            class_id=np.zeros(len(arr), dtype=int),
        )
        tracked = tracker.update(detections)

        frame_dets = []
        for box, conf, tid in zip(
            tracked.xyxy, tracked.confidence, tracked.tracker_id, strict=True
        ):
            tid = int(tid)
            if tid < 0:
                continue
            x1, y1, x2, y2 = (round(float(v), 1) for v in box)
            frame_dets.append(
                {
                    "id": tid,
                    "bbox": [x1, y1, x2, y2],
                    "foot_px": [round((x1 + x2) / 2, 1), y2],
                    "conf": round(float(conf), 3),
                }
            )
            span = spans.setdefault(
                tid, {"id": tid, "t_start": t, "t_end": t, "n_obs": 0, "_on_track": []}
            )
            span["t_end"] = t
            span["n_obs"] += 1
            span["_on_track"].append(_on_track_of(box, arr))
        frames_out.append({"frame": idx, "t": t, "detections": frame_dets})

    tracks = []
    for span in spans.values():
        span["on_track"] = round(float(np.median(span.pop("_on_track"))), 3)
        long_enough = span["t_end"] - span["t_start"] >= params.min_track_seconds
        if long_enough and span["on_track"] >= params.min_track_on_track:
            tracks.append(span)
    tracks.sort(key=lambda s: s["id"])
    valid_ids = {s["id"] for s in tracks}
    for f in frames_out:
        f["detections"] = [d for d in f["detections"] if d["id"] in valid_ids]

    return {
        "video": {
            "source": meta.source,
            "width": meta.width,
            "height": meta.height,
            "fps_src": round(meta.fps_src, 3),
            "fps_out": params.fps_out,
            "frames": len(frames_out),
            "duration_s": round(meta.duration_s, 3),
        },
        "pipeline": {
            "detector": model_id,
            "tracker": "bytetrack",
            "min_det_conf": params.min_det_conf,
            "min_on_track": params.min_on_track,
            "min_track_on_track": params.min_track_on_track,
            "roi": params.roi,
        },
        "tracks": tracks,
        "frames": frames_out,
    }
