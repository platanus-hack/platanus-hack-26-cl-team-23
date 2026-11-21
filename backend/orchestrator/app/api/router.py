from fastapi import APIRouter

from app.api.health_router import router as health_router
from app.api.narration_router import router as narration_router
from app.api.tracking_router import router as tracking_router
from app.api.zones_router import router as zones_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(narration_router)
api_router.include_router(tracking_router)
api_router.include_router(zones_router)
