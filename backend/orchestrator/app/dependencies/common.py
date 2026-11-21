import secrets
from collections.abc import Callable
from functools import cache
from typing import Annotated

import httpx
from fastapi import Depends, Header, Request

from app.clients.storage import Storage, build_storage
from app.core.config import Settings, settings
from app.core.domain_errors import AuthenticationError
from app.cv.detector import RoboflowDetector
from app.services.tracking_service import TrackingService


def get_settings() -> Settings:
    return settings


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


@cache
def get_storage() -> Storage:
    return build_storage()


@cache
def get_detector() -> RoboflowDetector:
    return RoboflowDetector(
        api_key=settings.roboflow_api_key,
        api_url=settings.roboflow_api_url,
        model_id=settings.roboflow_model_id,
    )


def get_detector_provider() -> Callable[[], RoboflowDetector]:
    return get_detector


def get_tracking_service(
    storage: Annotated[Storage, Depends(get_storage)],
    detector_provider: Annotated[Callable[[], RoboflowDetector], Depends(get_detector_provider)],
) -> TrackingService:
    return TrackingService(storage, detector_provider)


def require_demo_key(x_demo_key: Annotated[str | None, Header()] = None) -> None:
    """Protege los endpoints que gastan créditos de Roboflow si DEMO_ACCESS_KEY está definida."""
    expected = settings.demo_access_key
    if expected and not secrets.compare_digest(x_demo_key or "", expected):
        raise AuthenticationError("Falta o es inválido el header X-Demo-Key")
