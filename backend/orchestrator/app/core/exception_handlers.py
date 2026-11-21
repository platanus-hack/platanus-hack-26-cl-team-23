from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.domain_errors import DomainError
from app.core.logger import logger


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        content: dict[str, str] = {"detail": str(exc)}
        if exc.code:
            content["error_code"] = exc.code

        logger.warning(
            "%s %s -> %s: %s",
            request.method,
            request.url.path,
            exc.status_code,
            exc,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers or None,
        )
