from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.common import get_tactics_service
from app.schemas.tactics import TacticsRequest, TacticsResult
from app.services.tactics_service import TacticsService

router = APIRouter(prefix="/tactics", tags=["tactics"])

ServiceDep = Annotated[TacticsService, Depends(get_tactics_service)]


@router.post("/", response_model=TacticsResult)
async def tactics(request: TacticsRequest, service: ServiceDep) -> TacticsResult:
    """Pronóstico del final (P de ganar, de podio, llegada) y mejores momentos para adelantar."""
    return await service.tactics(request)
