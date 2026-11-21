from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.clients.http_client import create_http_client
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.http_client = create_http_client()
    logger.info("HTTP client initialized (env=%s)", settings.app_env)

    yield

    await app.state.http_client.aclose()
    logger.info("HTTP client closed")


def create_app() -> FastAPI:
    app = FastAPI(title="Orchestrator API", version="0.1.0", lifespan=lifespan)

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    return app


app = create_app()
