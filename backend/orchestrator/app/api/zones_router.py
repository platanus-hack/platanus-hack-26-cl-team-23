from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies.common import get_zones_service
from app.schemas.zones import ZoneFeaturesResponse, ZonesRequest, ZonesResult
from app.services.zones_service import ZonesService

router = APIRouter(prefix="/zones", tags=["zones"])

ServiceDep = Annotated[ZonesService, Depends(get_zones_service)]


@router.post("/features", response_model=ZoneFeaturesResponse)
async def features(
    service: ServiceDep,
    frames: Annotated[list[UploadFile], File(description="JPEG/PNG, uno por frame")],
    t: Annotated[list[float], Form(description="Segundos de cada frame, mismo orden")],
) -> ZoneFeaturesResponse:
    """Evidencia visual por frame (histograma de corte, apariencia, curvatura de líneas)."""
    images = [await frame.read() for frame in frames]
    return await service.features(images, t)


@router.post("/", response_model=ZonesResult)
async def zones(request: ZonesRequest, service: ServiceDep) -> ZonesResult:
    """En qué zona (Z1..Z6) de la pista enfoca la cámara en cada frame."""
    return await service.zones(request)
