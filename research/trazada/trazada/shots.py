"""Detector causal de cortes de plano en video de TV.

Compara cada frame con el anterior usando un histograma de color (tono, saturación) de la zona
útil de la imagen, sin los gráficos de TV (franja inferior y marcador). Un corte cambia el
contenido completo; un paneo, aunque sea rápido, mantiene los colores de la escena (tartán,
pasto, tribuna). En la final del 1500 separa los 14 cortes (distancia >= 0,25) de todos los
paneos y zooms (<= 0,14).

Solo mira hacia atrás: decide en el mismo frame en que llega el plano nuevo.
"""
from __future__ import annotations

import cv2
import numpy as np


class ShotDetector:
    def __init__(self, threshold: float = 0.19, min_gap_s: float = 0.5,
                 roi: tuple[float, float] = (60 / 720, 520 / 720)):
        self.threshold, self.min_gap_s, self.roi = threshold, min_gap_s, roi
        self._prev = None
        self._last_cut = -np.inf
        self.score = 0.0

    @staticmethod
    def hist(frame: np.ndarray, roi=(60 / 720, 520 / 720)) -> np.ndarray:
        h = frame.shape[0]
        small = cv2.resize(frame[int(roi[0] * h):int(roi[1] * h)], (192, 92), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
        return cv2.normalize(hist, hist)

    def __call__(self, frame: np.ndarray, t: float) -> bool:
        """True si este frame empieza un plano nuevo."""
        h = self.hist(frame, self.roi)
        cut = False
        if self._prev is not None:
            self.score = float(cv2.compareHist(self._prev, h, cv2.HISTCMP_BHATTACHARYYA))
            if self.score > self.threshold and t - self._last_cut >= self.min_gap_s:
                cut, self._last_cut = True, t
        self._prev = h
        return cut
