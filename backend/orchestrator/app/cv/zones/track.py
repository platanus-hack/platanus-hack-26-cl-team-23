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


STANDARD = Track()
