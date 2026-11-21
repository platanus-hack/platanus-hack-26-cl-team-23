from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health_service import health_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return health_service.check()
