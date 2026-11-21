"""Calibración cámara -> suelo con homografía.

El suelo de la pista es un plano, así que una homografía 3x3 lleva cada píxel del
suelo a metros. Se necesitan >= 4 correspondencias (píxel, punto conocido de la pista),
no colineales. Con más de 4 se usa RANSAC y se reporta el error de reproyección.

Los puntos conocidos se ingresan en coordenadas de pista (s, d) — p. ej. la línea de
meta cruzando el bordillo es (0, 0), y cruzando la línea entre pista 2 y 3 es (0, 2.44) —
o directamente en metros del mundo (x, y). Ver geometry.py para las convenciones.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .geometry import STANDARD, Track


@dataclass
class Calibration:
    H: np.ndarray                     # imagen (px) -> mundo (m)
    image_size: tuple[int, int]       # (w, h) del video calibrado
    image_pts: list = field(default_factory=list)
    world_pts: list = field(default_factory=list)
    rms_m: float = float("nan")       # error de reproyección en metros

    @property
    def H_inv(self) -> np.ndarray:
        return np.linalg.inv(self.H)

    def img_to_world(self, pts) -> np.ndarray:
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.H).reshape(-1, 2)

    def world_to_img(self, pts) -> np.ndarray:
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.H_inv).reshape(-1, 2)

    def scaled_to(self, w: int, h: int) -> "Calibration":
        """Misma calibración para un video del mismo encuadre a otra resolución."""
        sx, sy = self.image_size[0] / w, self.image_size[1] / h
        S = np.diag([sx, sy, 1.0])
        return Calibration(self.H @ S, (w, h), self.image_pts, self.world_pts, self.rms_m)

    # ---------- persistencia ----------
    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "H": self.H.tolist(), "image_size": list(self.image_size),
            "image_pts": [list(map(float, p)) for p in self.image_pts],
            "world_pts": [list(map(float, p)) for p in self.world_pts],
            "rms_m": self.rms_m,
        }, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Calibration":
        j = json.loads(Path(path).read_text())
        return cls(np.array(j["H"], dtype=np.float64), tuple(j["image_size"]),
                   j.get("image_pts", []), j.get("world_pts", []), j.get("rms_m", float("nan")))


def fit(image_pts, world_pts, image_size, ransac_thresh_m: float = 0.5) -> Calibration:
    img = np.asarray(image_pts, dtype=np.float64)
    wld = np.asarray(world_pts, dtype=np.float64)
    if len(img) < 4 or len(img) != len(wld):
        raise ValueError("Se necesitan >= 4 pares de puntos (imagen, mundo)")
    method = cv2.RANSAC if len(img) > 4 else 0
    H, _ = cv2.findHomography(img, wld, method, ransac_thresh_m)
    if H is None:
        raise ValueError("No se pudo calcular la homografía (¿puntos colineales?)")
    cal = Calibration(H / H[2, 2], tuple(image_size), img.tolist(), wld.tolist())
    err = np.linalg.norm(cal.img_to_world(img) - wld, axis=1)
    cal.rms_m = float(np.sqrt(np.mean(err ** 2)))
    return cal


def track_pts_to_world(sd_pts, track: Track = STANDARD) -> np.ndarray:
    sd = np.asarray(sd_pts, dtype=np.float64)
    x, y = track.track_to_world(sd[:, 0], sd[:, 1])
    return np.stack([x, y], axis=1)
