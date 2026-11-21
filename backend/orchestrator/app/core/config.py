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

        # Roboflow (opcionales: solo se exigen al procesar video, no al arrancar)
        self.roboflow_api_key: str = os.getenv("ROBOFLOW_API_KEY", "").strip()
        self.roboflow_api_url: str = os.getenv(
            "ROBOFLOW_API_URL", "https://serverless.roboflow.com"
        ).strip()
        self.roboflow_model_id: str = os.getenv("ROBOFLOW_MODEL_ID", "rfdetr-medium").strip()

        # Almacenamiento: Vercel Blob o disco local (auto = Blob solo si hay credenciales)
        self.blob_store_id: str = os.getenv("BLOB_STORE_ID", "").strip()
        self.blob_access: str = os.getenv("BLOB_ACCESS", "public").strip().lower()
        if self.blob_access not in {"public", "private"}:
            raise RuntimeError("Environment variable BLOB_ACCESS must be 'public' or 'private'")
        self.storage_backend: str = os.getenv("STORAGE_BACKEND", "auto").strip().lower()
        if self.storage_backend not in {"auto", "blob", "local"}:
            raise RuntimeError("Environment variable STORAGE_BACKEND must be auto, blob or local")
        self.local_storage_dir: Path = _PROJECT_ROOT / ".cache" / "storage"

        # Narración: Claude escribe el guion y ElevenLabs lo lee. Ambos opcionales:
        # sin credenciales el relato cae a plantillas y queda sin voz, sin romper la API.
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5").strip()
        self.eleven_labs_api_key: str = os.getenv("ELEVEN_LABS_API_KEY", "").strip()
        self.eleven_labs_voice_id: str = os.getenv(
            "ELEVEN_LABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
        ).strip()
        self.eleven_labs_model: str = os.getenv("ELEVEN_LABS_MODEL", "eleven_v4").strip()

        # Si se define, /detect y /process exigen el header X-Demo-Key
        self.demo_access_key: str = os.getenv("DEMO_ACCESS_KEY", "").strip()

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() == "local"


settings = Settings()
