import asyncio
import os
from pathlib import Path
from typing import Protocol

from vercel import blob

from app.core.config import settings
from app.core.logger import logger


class Storage(Protocol):
    async def get(self, pathname: str) -> bytes | None: ...

    async def put(self, pathname: str, data: bytes, content_type: str) -> str | None:
        """Guarda (sobrescribe) y devuelve la URL pública si el backend tiene una."""
        ...


def _safe_pathname(pathname: str) -> str:
    parts = pathname.split("/")
    if not pathname or pathname.startswith("/") or ".." in parts or "" in parts:
        raise ValueError(f"Ruta de almacenamiento inválida: {pathname!r}")
    return pathname


class LocalStorage:
    """Disco local: para desarrollo y tests, sin credenciales ni red."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, pathname: str) -> Path:
        return self._root / _safe_pathname(pathname)

    async def get(self, pathname: str) -> bytes | None:
        path = self._path(pathname)
        if not path.is_file():
            return None
        return await asyncio.to_thread(path.read_bytes)

    async def put(self, pathname: str, data: bytes, content_type: str) -> str | None:
        path = self._path(pathname)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return None


class BlobStorage:
    """Vercel Blob. En Vercel usa BLOB_STORE_ID + token OIDC automático."""

    def __init__(self, access: str) -> None:
        self._access = access

    async def get(self, pathname: str) -> bytes | None:
        try:
            result = await blob.get_blob(_safe_pathname(pathname), access=self._access)
        except blob.BlobNotFoundError:
            return None
        return result.body

    async def put(self, pathname: str, data: bytes, content_type: str) -> str | None:
        result = await blob.put_blob(
            _safe_pathname(pathname),
            data,
            access=self._access,
            content_type=content_type,
            allow_overwrite=True,
            cache_control_max_age=60,
        )
        return result.url


def _has_blob_credentials() -> bool:
    return bool(
        os.getenv("VERCEL")
        or os.getenv("VERCEL_OIDC_TOKEN")
        or os.getenv("BLOB_READ_WRITE_TOKEN")
        or os.getenv("VERCEL_BLOB_READ_WRITE_TOKEN")
    )


def build_storage() -> Storage:
    backend = settings.storage_backend
    use_blob = backend == "blob" or (
        backend == "auto" and settings.blob_store_id and _has_blob_credentials()
    )
    if use_blob:
        logger.info("Almacenamiento: Vercel Blob (%s)", settings.blob_access)
        return BlobStorage(settings.blob_access)
    logger.info("Almacenamiento: disco local (%s)", settings.local_storage_dir)
    return LocalStorage(settings.local_storage_dir)
