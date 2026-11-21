"""Suavizado por corredor en coordenadas de pista.

El punto de los pies sale ruidoso (la caja del detector "respira" con cada zancada),
así que cada ID lleva:
  - un filtro alfa-beta sobre s y d para la posición suavizada, y
  - la velocidad como pendiente de mínimos cuadrados de s sobre la última ventana
    (~1 s): sin sesgo, estable y con medio segundo de retraso, suficiente para tácticas.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .geometry import STANDARD, Track


@dataclass
class AlphaBeta:
    alpha: float = 0.35
    beta: float = 0.02
    x: float | None = None
    v: float = 0.0

    def update(self, z: float, dt: float, innovation: float | None = None) -> float:
        if self.x is None:
            self.x = z
            return self.x
        pred = self.x + self.v * dt
        r = (z - pred) if innovation is None else innovation
        self.x = pred + self.alpha * r
        if dt > 0:
            self.v += self.beta * r / dt
        return self.x


@dataclass
class RunnerFilter:
    track: Track = STANDARD
    window_s: float = 1.0
    s: AlphaBeta = field(default_factory=AlphaBeta)
    d: AlphaBeta = field(default_factory=lambda: AlphaBeta(alpha=0.25, beta=0.01))
    last_t: float | None = None
    distance: float = 0.0     # metros realmente recorridos (incluye lo que se abrió)
    progress: float = 0.0     # metros de progreso sobre la línea de medición
    hits: int = 0
    speed: float = 0.0        # m/s de progreso
    _hist: deque = field(default_factory=lambda: deque(maxlen=240))
    _s_unwrapped: float = 0.0
    _last_meas: float | None = None

    def update(self, s_meas: float, d_meas: float, t: float):
        dt = 0.0 if self.last_t is None else max(1e-3, t - self.last_t)
        self.last_t = t

        # historia de s "desenrollada" (sin salto 400 -> 0) para la velocidad
        if self._last_meas is not None:
            self._s_unwrapped += self.track.ds_wrap(self._last_meas, s_meas)
        self._last_meas = s_meas
        self._hist.append((t, self._s_unwrapped))
        while self._hist and t - self._hist[0][0] > self.window_s:
            self._hist.popleft()
        if len(self._hist) >= 4:
            h = np.asarray(self._hist)
            self.speed = float(np.polyfit(h[:, 0], h[:, 1], 1)[0])
        self.s.v = self.speed  # el alfa-beta predice con la velocidad robusta

        if self.s.x is None:
            self.s.update(s_meas, dt)
            self.d.update(d_meas, dt)
        else:
            pred_s = self.s.x + self.s.v * dt
            prev_s = self.s.x
            self.s.update(s_meas, dt, innovation=self.track.ds_wrap(pred_s, s_meas))
            self.s.x %= self.track.lap
            self.d.update(d_meas, dt)
            ds = self.track.ds_wrap(prev_s, self.s.x)
            self.progress += ds
            self.distance += abs(ds) * self.track.extra_distance_rate(self.s.x, self.d.x)
        self.hits += 1
        return self.s.x, self.d.x, self.speed

    @property
    def extra(self) -> float:
        """Metros de más respecto a haber corrido el mismo progreso por la cuerda."""
        return self.distance - abs(self.progress)
