import asyncio
import itertools

import cv2
import numpy as np

from app.core.domain_errors import ValidationDomainError
from app.cv.zones import pipeline
from app.cv.zones.layout import NAMES
from app.schemas.zones import (
    ZoneFeatures,
    ZoneFeaturesResponse,
    ZonesRequest,
    ZonesResult,
)

MAX_BATCH_FRAMES = 24
MAX_FRAME_BYTES = 1_500_000


def _decode_jpeg(data: bytes) -> np.ndarray:
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValidationDomainError("No se pudo decodificar uno de los frames (JPEG/PNG válido)")
    return frame


def _round(values: np.ndarray) -> list[float]:
    return [round(float(v), 4) for v in values]


class ZonesService:
    async def features(
        self,
        images: list[bytes],
        times: list[float],
        want_desc: list[bool] | None = None,
    ) -> ZoneFeaturesResponse:
        """Evidencia visual de un lote de frames (sin estado): corte, apariencia y curvatura.

        `want_desc` (uno por frame) marca en cuáles calcular apariencia y curvatura, que es lo
        caro; en los demás solo va el histograma. Sin él se calcula todo."""
        if not images:
            raise ValidationDomainError("Envía al menos un frame")
        if len(images) != len(times):
            raise ValidationDomainError("Debe haber un 't' por cada frame")
        if want_desc is not None and len(want_desc) != len(images):
            raise ValidationDomainError("Debe haber un 'want_desc' por cada frame")
        if len(images) > MAX_BATCH_FRAMES:
            raise ValidationDomainError(f"Máximo {MAX_BATCH_FRAMES} frames por petición")
        if any(len(img) > MAX_FRAME_BYTES for img in images):
            raise ValidationDomainError(f"Cada frame debe pesar menos de {MAX_FRAME_BYTES} bytes")

        def work() -> list[ZoneFeatures]:
            out = []
            for i, (img, t) in enumerate(zip(images, times, strict=True)):
                feats = pipeline.frame_features(
                    _decode_jpeg(img), full=want_desc is None or want_desc[i]
                )
                full = feats["desc"] is not None
                out.append(
                    ZoneFeatures(
                        t=t,
                        hist=_round(feats["hist"]),
                        desc=_round(feats["desc"]) if full else None,
                        bend=round(feats["bend"], 5) if full else None,
                        chord=round(feats["chord"], 1) if full else None,
                        n=feats["n"],
                    )
                )
            return out

        return ZoneFeaturesResponse(frames=await asyncio.to_thread(work))

    async def zones(self, request: ZonesRequest) -> ZonesResult:
        """Filtro de zonas sobre las features acumuladas (sin estado, sin llamadas externas)."""
        times = [f.t for f in request.frames]
        if any(b <= a for a, b in itertools.pairwise(times)):
            raise ValidationDomainError("'t' debe ser estrictamente creciente")

        features = [
            pipeline.FrameFeatures(
                t=f.t,
                hist=np.asarray(f.hist, dtype=np.float32),
                desc=None if f.desc is None else np.asarray(f.desc, dtype=np.float32),
                bend=f.bend,
                chord=f.chord,
                n=f.n,
            )
            for f in request.frames
        ]
        params = pipeline.ZoneParams(
            distance=request.distance,
            t0=request.t0,
            seed=request.seed,
            cut_threshold=request.cut_threshold,
        )
        out = await asyncio.to_thread(pipeline.run, features, params)
        return ZonesResult(
            distance=request.distance,
            t0=request.t0,
            zone_names=NAMES,
            cuts=out.cuts,
            frames=out.frames,
        )
