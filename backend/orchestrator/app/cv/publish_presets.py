"""Uso: uv run python -m app.cv.publish_presets [--assets app/assets]

Sube los videos de ejemplo y sus resultados precomputados al almacenamiento configurado
(Vercel Blob o disco local, ver STORAGE_BACKEND) bajo `presets/`. Los archivos locales viven
en `app/assets/` (fuera de git): <assets>/<NAME>.mp4 y <assets>/out/<NAME>.tracks.json.
"""

import argparse
import asyncio
from pathlib import Path

from app.clients.storage import build_storage
from app.core.logger import logger
from app.services.tracking_service import PRESET_VIDEOS


async def publish(assets: Path) -> None:
    storage = build_storage()
    for name, video in PRESET_VIDEOS.items():
        uploads = [
            (assets / video, f"presets/{video}", "video/mp4"),
            (
                assets / "out" / f"{name}.tracks.json",
                f"presets/{name}.tracks.json",
                "application/json",
            ),
        ]
        for path, pathname, content_type in uploads:
            if not path.is_file():
                logger.warning("Omitido (no existe): %s", path)
                continue
            url = await storage.put(pathname, path.read_bytes(), content_type)
            logger.info("Publicado %s%s", pathname, f" -> {url}" if url else "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path("app/assets"))
    asyncio.run(publish(parser.parse_args().assets))


if __name__ == "__main__":
    main()
