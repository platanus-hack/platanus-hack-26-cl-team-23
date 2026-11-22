"""Geometría nominal de la pista de 400 m (World Athletics).

`s` son los metros desde la meta en sentido de carrera sobre la línea de medición de la pista 1
(0 <= s < 400). Valores estándar; verificar contra el certificado de la pista real.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    radius: float = 36.5
    straight: float = 84.39
    meas_offset: float = 0.30

    @property
    def curve_len(self) -> float:
        return math.pi * (self.radius + self.meas_offset)

    @property
    def lap(self) -> float:
        return 2 * self.straight + 2 * self.curve_len

    def in_curve(self, s: float) -> bool:
        u = s % self.lap
        c = self.curve_len
        return u < c or c + self.straight <= u < 2 * c + self.straight

    def extra_distance_rate(self, s: float, d: float) -> float:
        """Metros recorridos por cada metro de progreso: > 1 en curva si va por fuera."""
        if self.in_curve(s):
            return (self.radius + d) / (self.radius + self.meas_offset)
        return 1.0


STANDARD = Track()
