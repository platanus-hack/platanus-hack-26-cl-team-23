from app.core.config import settings
from app.schemas.health import HealthResponse

APP_VERSION = "0.1.0"


class HealthService:
    def check(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            env=settings.app_env,
            version=APP_VERSION,
        )


health_service = HealthService()
