import asyncio
import hashlib
import itertools
import json
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from app.clients.storage import Storage
from app.core.config import settings
from app.core.domain_errors import ExternalServiceError, NotFoundError, ValidationDomainError
from app.cv import pipeline
from app.cv.detector import DetectorError, RoboflowDetector
from app.schemas.tracking import (
    DetectedFrame,
    DetectResponse,
    ProcessRequest,
    ProcessResponse,
    TrackingResult,
    TrackRequest,
)

PRESET_VIDEOS = {"NCCA": "NCCA.mp4"}

MAX_BATCH_FRAMES = 24
MAX_FRAME_BYTES = 1_500_000
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_DURATION_S = 40.0
MAX_INLINE_RESULT_BYTES = 2_000_000

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", value)


def _decode_jpeg(data: bytes) -> np.ndarray:
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValidationDomainError("No se pudo decodificar uno de los frames (JPEG/PNG válido)")
    return frame


class TrackingService:
    def __init__(self, storage: Storage, detector_provider: Callable[[], RoboflowDetector]) -> None:
        self._storage = storage
        self._detector_provider = detector_provider

    def _detector(self) -> RoboflowDetector:
        try:
            return self._detector_provider()
        except DetectorError as exc:
            raise ExternalServiceError(str(exc), code="detector_unavailable") from exc

    async def detect_batch(
        self,
        images: list[bytes],
        times: list[float],
        orig_width: int,
        orig_height: int,
    ) -> DetectResponse:
        """Detecta en paralelo un lote de frames y devuelve cajas en píxeles del video original."""
        if not images:
            raise ValidationDomainError("Envía al menos un frame")
        if len(images) != len(times):
            raise ValidationDomainError("Debe haber un 't' por cada frame")
        if len(images) > MAX_BATCH_FRAMES:
            raise ValidationDomainError(f"Máximo {MAX_BATCH_FRAMES} frames por petición")
        if any(len(img) > MAX_FRAME_BYTES for img in images):
            raise ValidationDomainError(f"Cada frame debe pesar menos de {MAX_FRAME_BYTES} bytes")

        detector = self._detector()

        def work() -> list[DetectedFrame]:
            frames = [_decode_jpeg(img) for img in images]
            raw = detector.detect_many(frames)
            out: list[DetectedFrame] = []
            for frame, dets, t in zip(frames, raw, times, strict=True):
                height, width = frame.shape[:2]
                sx, sy = orig_width / width, orig_height / height
                scored = pipeline.score_frame(frame, dets)
                out.append(
                    DetectedFrame(
                        t=t,
                        dets=[
                            [
                                round(d[0] * sx, 1),
                                round(d[1] * sy, 1),
                                round(d[2] * sx, 1),
                                round(d[3] * sy, 1),
                                round(d[4], 3),
                                d[5],
                            ]
                            for d in scored
                        ],
                    )
                )
            return out

        try:
            frames_out = await asyncio.to_thread(work)
        except DetectorError as exc:
            raise ExternalServiceError(str(exc), code="detector_failed") from exc
        return DetectResponse(model=detector.model_id, frames=frames_out)

    async def track(self, request: TrackRequest) -> TrackingResult:
        """ByteTrack sobre detecciones ya hechas (sin estado, sin llamadas externas)."""
        times = [f.t for f in request.frames]
        if any(b <= a for a, b in itertools.pairwise(times)):
            raise ValidationDomainError("'t' debe ser estrictamente creciente")

        meta = pipeline.VideoMeta(
            source=request.source,
            width=request.width,
            height=request.height,
            fps_src=request.fps_src or request.fps_out,
            duration_s=times[-1],
        )
        result = await asyncio.to_thread(
            pipeline.track,
            meta,
            list(range(len(times))),
            times,
            [f.dets for f in request.frames],
            pipeline.TrackingParams(fps_out=request.fps_out),
            settings.roboflow_model_id,
        )
        return TrackingResult.model_validate(result)

    async def _load_video(self, request: ProcessRequest) -> tuple[bytes, str]:
        if request.source is not None:
            filename = PRESET_VIDEOS.get(request.source)
            if filename is None:
                raise NotFoundError(f"Video de ejemplo desconocido: {request.source!r}")
            data = await self._storage.get(f"presets/{filename}")
            if data is None:
                raise NotFoundError(
                    f"El video de ejemplo {request.source!r} no está en el almacenamiento"
                )
            return data, filename

        pathname = request.blob or ""
        if not pathname.startswith("videos/"):
            raise ValidationDomainError("'blob' debe empezar con 'videos/'")
        try:
            data = await self._storage.get(pathname)
        except ValueError as exc:
            raise ValidationDomainError(str(exc)) from exc
        if data is None:
            raise NotFoundError(f"No existe el video {pathname!r} en el almacenamiento")
        if len(data) > MAX_VIDEO_BYTES:
            raise ValidationDomainError(f"El video supera {MAX_VIDEO_BYTES // 1024 // 1024} MB")
        return data, Path(pathname).name

    @staticmethod
    def _probe(video_path: Path) -> pipeline.VideoMeta:
        try:
            meta = pipeline.read_meta(video_path)
        except FileNotFoundError as exc:
            raise ValidationDomainError(
                "No se pudo leer el video (formato o códec no soportado)"
            ) from exc
        if meta.fps_src <= 0 or meta.duration_s <= 0:
            raise ValidationDomainError("El video no tiene fps o duración válidos")
        if meta.duration_s > MAX_DURATION_S:
            raise ValidationDomainError(
                f"El video dura {meta.duration_s:.0f} s; el máximo es {MAX_DURATION_S:.0f} s"
            )
        return meta

    async def process(self, request: ProcessRequest) -> ProcessResponse:
        """Pipeline completo sobre un video: detecta en paralelo, filtra y trackea."""
        data, filename = await self._load_video(request)
        model_id = settings.roboflow_model_id
        key = f"{hashlib.sha256(data).hexdigest()[:16]}_{request.fps:g}fps_{_slug(model_id)}"
        result_path = f"cache/{key}.tracks.json"
        detections_path = f"cache/{key}.detections.json"

        stored = await self._storage.get(result_path)
        if stored is not None:
            return self._response(key, True, result_path, None, stored)

        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / filename
            await asyncio.to_thread(video_path.write_bytes, data)
            meta = await asyncio.to_thread(self._probe, video_path)

            cached_detections = await self._storage.get(detections_path)
            if cached_detections is not None:
                payload = json.loads(cached_detections)
                indices, raw = payload["indices"], payload["detections"]
            else:
                detector = self._detector()
                try:
                    _, indices, raw = await asyncio.to_thread(
                        pipeline.detect_video, video_path, detector, request.fps
                    )
                except DetectorError as exc:
                    raise ExternalServiceError(str(exc), code="detector_failed") from exc
                await self._storage.put(
                    detections_path,
                    json.dumps({"indices": indices, "detections": raw}).encode(),
                    "application/json",
                )
            scored = await asyncio.to_thread(pipeline.score_on_track, video_path, indices, raw)

        result = await asyncio.to_thread(
            pipeline.track,
            meta,
            indices,
            [i / meta.fps_src for i in indices],
            scored,
            pipeline.TrackingParams(fps_out=request.fps),
            model_id,
        )
        payload_bytes = json.dumps(result, separators=(",", ":")).encode()
        url = await self._storage.put(result_path, payload_bytes, "application/json")
        return self._response(key, False, result_path, url, payload_bytes)

    @staticmethod
    def _response(
        key: str, cached: bool, result_path: str, url: str | None, payload: bytes
    ) -> ProcessResponse:
        inline = (
            TrackingResult.model_validate_json(payload)
            if len(payload) <= MAX_INLINE_RESULT_BYTES
            else None
        )
        return ProcessResponse(
            key=key, cached=cached, result_path=result_path, result_url=url, result=inline
        )

    async def get_result(self, key: str) -> bytes:
        if not _KEY_PATTERN.fullmatch(key):
            raise ValidationDomainError("Clave de resultado inválida")
        data = await self._storage.get(f"cache/{key}.tracks.json")
        if data is None:
            raise NotFoundError(f"No hay resultado para la clave {key!r}")
        return data

    async def get_preset(self, name: str) -> bytes:
        if name not in PRESET_VIDEOS:
            raise NotFoundError(f"Preset desconocido: {name!r}")
        data = await self._storage.get(f"presets/{name}.tracks.json")
        if data is None:
            raise NotFoundError(f"El preset {name!r} aún no fue publicado")
        return data
