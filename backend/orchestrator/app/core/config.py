import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _require_int(name: str) -> int:
    value = _require(name)
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def _require_float(name: str) -> float:
    value = _require(name)
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be a number") from exc


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_bool(name: str, value: str) -> bool:
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise RuntimeError(
        f"Environment variable {name} must be a boolean: true/false, 1/0, yes/no, on/off"
    )


def _require_bool(name: str) -> bool:
    return _parse_bool(name, _require(name))


class Settings:
    """Configuración de la aplicación leída desde variables de entorno / .env."""

    def __init__(self) -> None:
        # Runtime
        self.app_env: str = _require("APP_ENV")
        self.app_host: str = _require("APP_HOST")
        self.app_port: int = _require_int("APP_PORT")

        # HTTP client
        self.http_timeout: float = _require_float("HTTP_TIMEOUT")

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() == "local"


settings = Settings()
