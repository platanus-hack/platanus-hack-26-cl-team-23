from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies.common import get_athletes_service
from app.schemas.athletes import AthleteFeaturesResponse, AthletesRequest, AthletesResult
from app.services.athletes_service import AthletesService

router = APIRouter(prefix="/athletes", tags=["athletes"])

ServiceDep = Annotated[AthletesService, Depends(get_athletes_service)]


@router.post("/features", response_model=AthleteFeaturesResponse)
async def features(
    service: ServiceDep,
    frames: Annotated[list[UploadFile], File(description="JPEG/PNG, uno por frame, consecutivos")],
    t: Annotated[list[float], Form(description="Segundos de cada frame, mismo orden")],
    boxes: Annotated[
        str, Form(description="JSON por frame: [[id, x1, y1, x2, y2], ...] (salida de /track)")
    ],
    orig_width: Annotated[int | None, Form(description="Ancho del video original")] = None,
    orig_height: Annotated[int | None, Form(description="Alto del video original")] = None,
) -> AthleteFeaturesResponse:
    """Medición por frame: posición de cada corredor relativa al grupo y al bordillo."""
    images = [await frame.read() for frame in frames]
    return await service.features(images, t, boxes, orig_width, orig_height)


@router.post("/", response_model=AthletesResult)
async def athletes(request: AthletesRequest, service: ServiceDep) -> AthletesResult:
    """Posición y velocidad de cada atleta respecto a la cancha (grupo + relativo al grupo)."""
    return await service.athletes(request)
