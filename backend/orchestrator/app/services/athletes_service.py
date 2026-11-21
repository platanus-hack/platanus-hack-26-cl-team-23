import asyncio
import itertools
import json

import cv2
import numpy as np

from app.core.domain_errors import ValidationDomainError
from app.cv.athletes import pipeline
from app.schemas.athletes import (
    AthleteFeaturesResponse,
    AthleteFrameFeatures,
    AthletesRequest,
    AthletesResult,
    RunnerFeatures,
)

MAX_BATCH_FRAMES = 24
MAX_FRAME_BYTES = 1_500_000


def _decode_jpeg(data: bytes) -> np.ndarray:
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValidationDomainError("No se pudo decodificar uno de los frames (JPEG/PNG válido)")
    return frame


def _parse_boxes(raw: str, n_frames: int) -> list[list[list[float]]]:
    try:
        boxes = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationDomainError(
            "'boxes' debe ser JSON: [[[id,x1,y1,x2,y2], ...], ...]"
        ) from exc
    if not isinstance(boxes, list) or len(boxes) != n_frames:
        raise ValidationDomainError("'boxes' debe tener una lista de cajas por frame")
    for frame_boxes in boxes:
        if not isinstance(frame_boxes, list) or any(
            not isinstance(b, list) or len(b) != 5 for b in frame_boxes
        ):
            raise ValidationDomainError("Cada caja debe ser [id, x1, y1, x2, y2]")
    return boxes


class AthletesService:
    async def features(
        self,
        images: list[bytes],
        times: list[float],
        boxes_json: str,
        orig_width: int | None = None,
        orig_height: int | None = None,
    ) -> AthleteFeaturesResponse:
        """Medición por frame de un lote (sin estado): Δs y d de cada corredor, color de camiseta
        y movimiento del fondo entre frames consecutivos del lote."""
        if not images:
            raise ValidationDomainError("Envía al menos un frame")
        if len(images) != len(times):
            raise ValidationDomainError("Debe haber un 't' por cada frame")
        if len(images) > MAX_BATCH_FRAMES:
            raise ValidationDomainError(f"Máximo {MAX_BATCH_FRAMES} frames por petición")
        if any(len(img) > MAX_FRAME_BYTES for img in images):
            raise ValidationDomainError(f"Cada frame debe pesar menos de {MAX_FRAME_BYTES} bytes")
        if any(b <= a for a, b in itertools.pairwise(times)):
            raise ValidationDomainError("'t' debe ser estrictamente creciente")
        boxes = _parse_boxes(boxes_json, len(images))

        def work() -> list[AthleteFrameFeatures]:
            frames = [_decode_jpeg(img) for img in images]
            scaled = []
            for frame, fb in zip(frames, boxes, strict=True):
                # cajas en píxeles del video original -> píxeles del JPEG recibido
                sx = frame.shape[1] / orig_width if orig_width else 1.0
                sy = frame.shape[0] / orig_height if orig_height else 1.0
                scaled.append([[b[0], b[1] * sx, b[2] * sy, b[3] * sx, b[4] * sy] for b in fb])
            feats = pipeline.frame_features(frames, times, scaled)
            out = []
            for f, frame in zip(feats, frames, strict=True):
                sx = orig_width / frame.shape[1] if orig_width else 1.0
                sy = orig_height / frame.shape[0] if orig_height else 1.0
                out.append(
                    AthleteFrameFeatures(
                        t=f.t,
                        u_img=None if f.u_img is None else [round(v, 5) for v in f.u_img],
                        head_on=f.head_on,
                        blind=f.blind,
                        bg_shift=None
                        if f.bg_shift is None
                        else [round(f.bg_shift[0] * sx, 2), round(f.bg_shift[1] * sy, 2)],
                        runners=[
                            RunnerFeatures(
                                id=r.id,
                                bbox=[
                                    round(r.bbox[0] * sx, 1),
                                    round(r.bbox[1] * sy, 1),
                                    round(r.bbox[2] * sx, 1),
                                    round(r.bbox[3] * sy, 1),
                                ],
                                foot=[round(r.foot[0] * sx, 1), round(r.foot[1] * sy, 1)],
                                ds=round(r.ds, 3),
                                sigma_ds=round(r.sigma_ds, 3),
                                d=None if r.d is None else round(r.d, 3),
                                sigma_d=None if r.sigma_d is None else round(r.sigma_d, 3),
                                jersey=None
                                if r.jersey is None
                                else [round(float(v), 4) for v in r.jersey],
                            )
                            for r in f.runners
                        ],
                    )
                )
            return out

        return AthleteFeaturesResponse(frames=await asyncio.to_thread(work))

    async def athletes(self, request: AthletesRequest) -> AthletesResult:
        """Posición y velocidad de cada atleta (sin estado, sin llamadas externas)."""
        if len(request.frames) != len(request.group):
            raise ValidationDomainError(
                "'group' debe tener una fila por frame (la salida de /zones)"
            )
        times = [f.t for f in request.frames]
        if any(b <= a for a, b in itertools.pairwise(times)):
            raise ValidationDomainError("'t' debe ser estrictamente creciente")
        features = [
            pipeline.AthleteFrameFeatures(
                t=f.t,
                u_img=f.u_img,
                head_on=f.head_on,
                blind=f.blind,
                bg_shift=f.bg_shift,
                runners=[
                    pipeline.RunnerFeatures(
                        id=r.id,
                        bbox=r.bbox,
                        foot=r.foot,
                        ds=r.ds,
                        sigma_ds=r.sigma_ds,
                        d=r.d,
                        sigma_d=r.sigma_d,
                        jersey=None if r.jersey is None else np.asarray(r.jersey, dtype=np.float32),
                    )
                    for r in f.runners
                ],
            )
            for f in request.frames
        ]
        group = [pipeline.GroupState(x=g.x, v=g.v, cut=g.cut) for g in request.group]
        params = pipeline.AthleteParams(t0=request.t0, field_size=request.field_size)
        frames = await asyncio.to_thread(pipeline.run, features, group, params)
        return AthletesResult(t0=request.t0, frames=frames)
