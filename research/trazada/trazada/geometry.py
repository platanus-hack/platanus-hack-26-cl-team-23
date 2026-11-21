"""Geometría de una pista de atletismo estándar de 400 m (World Athletics).

Sistema de coordenadas "mundo" (metros, vista cenital, eje y hacia arriba):
  - Origen en el centro de la pista (centro del rectángulo del pasto).
  - Las rectas son paralelas al eje x. Los centros de las curvas están en (±STRAIGHT/2, 0).
  - Se corre en sentido antihorario: recta principal abajo (y < 0) hacia +x.

Sistema de coordenadas "pista" (s, d):
  - s: progreso en metros, medido sobre la línea de medición de la pista 1
       (0,30 m del bordillo). s = 0 en la línea de meta (fin de la recta principal),
       crece en sentido de carrera, 0 <= s < 400.
  - d: distancia lateral al bordillo interior en metros (d < 0 = dentro del pasto).
       Pista n ocupa d in [(n-1)*LANE, n*LANE).

Con (s, d) se responde directo a "en qué pista va", "cuánto le falta" y
"cuánto se abrió" — que es lo que importa para la decisión táctica.

Nota: valores nominales de la pista estándar; verificar contra el certificado de
la pista real (hay pistas con radios distintos, p. ej. 36,80 m o "doble curva").
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Track:
    radius: float = 36.5          # radio del bordillo interior
    straight: float = 84.39       # largo de cada recta
    lane_width: float = 1.22
    lanes: int = 8
    meas_offset: float = 0.30     # línea de medición de la pista 1

    @property
    def r_meas(self) -> float:
        return self.radius + self.meas_offset

    @property
    def curve_len(self) -> float:
        return math.pi * self.r_meas

    @property
    def lap(self) -> float:
        return 2 * self.straight + 2 * self.curve_len

    # Límites de cada tramo en s
    @property
    def bounds(self):
        c, l = self.curve_len, self.straight
        return {"curva1": (0, c), "recta_opuesta": (c, c + l), "curva2": (c + l, 2 * c + l), "recta_principal": (2 * c + l, 2 * c + 2 * l)}

    def segment(self, s: float) -> str:
        s = s % self.lap
        for name, (a, b) in self.bounds.items():
            if a <= s < b:
                return name
        return "recta_principal"

    def lane_of(self, d: float) -> int:
        """Pista (1..lanes) para una distancia lateral; 0 si está dentro del pasto."""
        if d < 0:
            return 0
        return int(min(self.lanes, d // self.lane_width + 1))

    # ---------------- conversiones ----------------
    def world_to_track(self, x, y):
        """(x, y) en metros -> (s, d). Acepta escalares o arrays."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        h, c, l, R, Rm = self.straight / 2, self.curve_len, self.straight, self.radius, self.r_meas

        s = np.empty(np.broadcast(x, y).shape)
        d = np.empty_like(s)
        x, y = np.broadcast_to(x, s.shape), np.broadcast_to(y, s.shape)

        m1 = x > h                     # curva 1 (derecha)
        m2 = x < -h                    # curva 2 (izquierda)
        mb = ~m1 & ~m2 & (y >= 0)      # recta opuesta
        mh = ~m1 & ~m2 & (y < 0)       # recta principal

        th = np.arctan2(y[m1], x[m1] - h)                       # -pi/2 .. pi/2
        s[m1] = (th + math.pi / 2) * Rm
        d[m1] = np.hypot(x[m1] - h, y[m1]) - R

        s[mb] = c + (h - x[mb])
        d[mb] = y[mb] - R

        ph = np.mod(np.arctan2(y[m2], x[m2] + h), 2 * math.pi)  # pi/2 .. 3pi/2
        s[m2] = c + l + (ph - math.pi / 2) * Rm
        d[m2] = np.hypot(x[m2] + h, y[m2]) - R

        s[mh] = 2 * c + l + (x[mh] + h)
        d[mh] = -y[mh] - R

        s = np.mod(s, self.lap)
        if s.ndim == 0:
            return float(s), float(d)
        return s, d

    def track_to_world(self, s, d):
        """(s, d) -> (x, y) en metros. Acepta escalares o arrays."""
        s = np.mod(np.asarray(s, dtype=float), self.lap)
        d = np.asarray(d, dtype=float)
        s, d = np.broadcast_arrays(s, d)
        h, c, l, R, Rm = self.straight / 2, self.curve_len, self.straight, self.radius, self.r_meas
        x = np.empty(s.shape)
        y = np.empty(s.shape)
        r = R + d

        m1 = s < c
        mb = (s >= c) & (s < c + l)
        m2 = (s >= c + l) & (s < 2 * c + l)
        mh = s >= 2 * c + l

        th = s[m1] / Rm - math.pi / 2
        x[m1], y[m1] = h + r[m1] * np.cos(th), r[m1] * np.sin(th)
        x[mb], y[mb] = h - (s[mb] - c), r[mb]
        ph = (s[m2] - c - l) / Rm + math.pi / 2
        x[m2], y[m2] = -h + r[m2] * np.cos(ph), r[m2] * np.sin(ph)
        x[mh], y[mh] = -h + (s[mh] - 2 * c - l), -r[mh]

        if x.ndim == 0:
            return float(x), float(y)
        return x, y

    def ds_wrap(self, a: float, b: float) -> float:
        """Diferencia b - a en s, con el salto de 400 -> 0 resuelto."""
        return (b - a + self.lap / 2) % self.lap - self.lap / 2

    def extra_distance_rate(self, s: float, d: float) -> float:
        """Metros recorridos por cada metro de progreso. >1 en curva si va por fuera."""
        if self.segment(s).startswith("curva"):
            return (self.radius + d) / self.r_meas
        return 1.0


STANDARD = Track()
