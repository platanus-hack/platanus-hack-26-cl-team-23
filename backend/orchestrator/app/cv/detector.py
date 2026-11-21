import threading
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from itertools import islice

import numpy as np
from inference_sdk import InferenceConfiguration, InferenceHTTPClient

from app.core.logger import logger

PERSON_CLASS = "person"


class DetectorError(RuntimeError):
    pass


def _chunks(items: Iterable[np.ndarray], size: int) -> Iterator[list[np.ndarray]]:
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk


class RoboflowDetector:
    """Detecta personas llamando a la API serverless de Roboflow (sin modelo local)."""

    def __init__(
        self,
        api_key: str,
        api_url: str,
        model_id: str,
        min_conf: float = 0.2,
        max_workers: int = 8,
        retries: int = 4,
    ) -> None:
        if not api_key:
            raise DetectorError("ROBOFLOW_API_KEY está vacío")
        self.model_id = model_id
        self._api_key = api_key
        self._api_url = api_url
        self._min_conf = min_conf
        self._max_workers = max_workers
        self._retries = retries
        self._local = threading.local()

    def _client(self) -> InferenceHTTPClient:
        client = getattr(self._local, "client", None)
        if client is None:
            client = InferenceHTTPClient(api_url=self._api_url, api_key=self._api_key).configure(
                InferenceConfiguration(
                    api_key_transport="header",
                    confidence_threshold=self._min_conf,
                )
            )
            self._local.client = client
        return client

    def detect(self, frame: np.ndarray) -> list[list[float]]:
        """Devuelve [[x1, y1, x2, y2, conf], ...] solo de personas."""
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                result = self._client().infer(frame, model_id=self.model_id)
                return [
                    [
                        p["x"] - p["width"] / 2,
                        p["y"] - p["height"] / 2,
                        p["x"] + p["width"] / 2,
                        p["y"] + p["height"] / 2,
                        p["confidence"],
                    ]
                    for p in result["predictions"]
                    if p["class"] == PERSON_CLASS
                ]
            except Exception as exc:  # noqa: BLE001 - reintentamos cualquier fallo de red/API
                last_error = exc
                time.sleep(0.5 * 2**attempt)
        raise DetectorError(f"Falló la detección tras {self._retries} intentos: {last_error}")

    def detect_many(
        self,
        frames: Iterable[np.ndarray],
        on_progress: Callable[[int], None] | None = None,
    ) -> list[list[list[float]]]:
        """Detecta en paralelo conservando el orden. Procesa por bloques para acotar memoria."""
        results: list[list[list[float]]] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            for chunk in _chunks(frames, self._max_workers * 4):
                results.extend(pool.map(self.detect, chunk))
                if on_progress:
                    on_progress(len(results))
        logger.info("Detección completa: %d frames (modelo=%s)", len(results), self.model_id)
        return results
