import httpx
from fastapi import Request

from app.core.config import Settings, settings


def get_settings() -> Settings:
    return settings


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client
