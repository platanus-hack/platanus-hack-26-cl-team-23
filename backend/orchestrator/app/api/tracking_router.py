import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.core.logger import logger
from app.dependencies.common import get_tracking_service, get_zones_service, require_demo_key
from app.schemas.tracking import (
    AnalyzeResponse,
    DetectResponse,
    ProcessRequest,
    ProcessResponse,
    TrackingResult,
    TrackRequest,
)
from app.services.tracking_service import TrackingService
from app.services.zones_service import ZonesService

router = APIRouter(prefix="/tracking", tags=["tracking"])

ServiceDep = Annotated[TrackingService, Depends(get_tracking_service)]
ZonesDep = Annotated[ZonesService, Depends(get_zones_service)]
DemoKey = Depends(require_demo_key)


def _json(content: bytes, cache_control: str) -> Response:
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": cache_control},
    )


@router.post("/detect", response_model=DetectResponse, dependencies=[DemoKey])
async def detect(
    service: ServiceDep,
    frames: Annotated[list[UploadFile], File(description="JPEG/PNG, uno por frame")],
    t: Annotated[list[float], Form(description="Segundos de cada frame, mismo orden")],
    orig_width: Annotated[int, Form(gt=0, description="Ancho del video original")],
    orig_height: Annotated[int, Form(gt=0, description="Alto del video original")],
) -> DetectResponse:
    """Detección paralela de un lote de frames. Las cajas vuelven en píxeles del video original."""
    images = [await frame.read() for frame in frames]
    return await service.detect_batch(images, t, orig_width, orig_height)


@router.post("/analyze", response_model=AnalyzeResponse, dependencies=[DemoKey])
async def analyze(
    service: ServiceDep,
    zones_service: ZonesDep,
    frames: Annotated[list[UploadFile], File(description="JPEG/PNG, uno por frame")],
    t: Annotated[list[float], Form(description="Segundos de cada frame, mismo orden")],
    orig_width: Annotated[int, Form(gt=0, description="Ancho del video original")],
    orig_height: Annotated[int, Form(gt=0, description="Alto del video original")],
    with_zones: Annotated[bool, Form(description="También evidencia de zonas")] = True,
) -> AnalyzeResponse:
    """/detect y /zones/features en una sola petición: cada frame viaja una vez, no dos."""
    images = [await frame.read() for frame in frames]
    detect, zones = await asyncio.gather(
        service.detect_batch(images, t, orig_width, orig_height),
        zones_service.features(images, t) if with_zones else _none(),
        return_exceptions=True,
    )
    if isinstance(detect, BaseException):
        raise detect
    if isinstance(zones, BaseException):
        logger.warning("Zonas: la evidencia del lote falló (%s)", zones)
        zones = None
    return AnalyzeResponse(detect=detect, zones=zones)


async def _none() -> None:
    return None


@router.post("/track", response_model=TrackingResult)
async def track(request: TrackRequest, service: ServiceDep) -> TrackingResult:
    """ByteTrack sobre las detecciones acumuladas (sin estado ni llamadas externas)."""
    return await service.track(request)


@router.post("/process", response_model=ProcessResponse, dependencies=[DemoKey])
async def process(request: ProcessRequest, service: ServiceDep) -> ProcessResponse:
    """Pipeline completo sobre un video de ejemplo o de Blob: detecta, filtra y trackea."""
    return await service.process(request)


@router.get("/presets/{name}", response_model=TrackingResult)
async def preset(name: str, service: ServiceDep) -> Response:
    """Resultado precomputado de un video de ejemplo (la demo que no puede fallar)."""
    return _json(await service.get_preset(name), "public, max-age=3600")


@router.get("/results/{key}", response_model=TrackingResult)
async def result(key: str, service: ServiceDep) -> Response:
    """Resultado guardado por /process."""
    return _json(await service.get_result(key), "public, max-age=60")
