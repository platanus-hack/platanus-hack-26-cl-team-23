from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.dependencies.common import get_narration_service
from app.schemas.narration import NarrationRequest, NarrationResponse
from app.services.narration_service import NarrationService

router = APIRouter(prefix="/narration", tags=["narration"])

ServiceDep = Annotated[NarrationService, Depends(get_narration_service)]


@router.post("/", response_model=NarrationResponse)
async def narrate(request: NarrationRequest, service: ServiceDep) -> NarrationResponse:
    """Relato del clip: hechos → guion → voz. Repetir el mismo video sale de caché."""
    return await service.narrate(request)


@router.get(
    "/{key}/audio/{index}",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def audio(key: str, index: int, service: ServiceDep) -> Response:
    """Audio de un tramo del relato."""
    return Response(
        content=await service.audio(key, index),
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )
