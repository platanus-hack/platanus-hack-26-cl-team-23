"""Filtro causal de "en qué zona de la pista enfoca la cámara".

Cada partícula lleva x = metros recorridos desde la salida por el punto que enfoca la cámara
(sin envolver) y v = su velocidad; la zona sale de s = salida + x. El orden Z1 -> Z6 y cuánto dura
cada zona salen solos de `x += v·dt`, sin modelar transiciones.

Solo usa el presente y el pasado: predict(t) -> on_cut() -> update(likelihood) -> estimate().
"""

from collections.abc import Callable

import numpy as np

from app.cv.zones.layout import DEFAULT_PACE, PACE, start_s, zone_of
from app.cv.zones.track import STANDARD, Track

Likelihood = Callable[[np.ndarray], np.ndarray]


class ZoneFilter:
    def __init__(
        self,
        distance: float = 1500,
        track: Track = STANDARD,
        n: int = 4000,
        pace: tuple[float, float] | None = None,
        v_walk: float = 0.04,
        x_walk: float = 0.3,
        seed: int = 0,
    ) -> None:
        self.track, self.distance = track, distance
        self.s0 = start_s(distance, track)
        self.rng = np.random.default_rng(seed)
        lo, hi = pace or PACE.get(int(distance), DEFAULT_PACE)
        self.n = n
        self.x = np.zeros(n)
        self.v = self.rng.uniform(lo, hi, n)
        self.w = np.full(n, 1.0 / n)
        self.v_walk = v_walk  # m/s por √s: el ritmo cambia despacio
        self.x_walk = x_walk  # m por √s: la cámara no sigue exactamente al líder
        self.t = 0.0

    def predict(self, t: float) -> None:
        dt = t - self.t
        if dt <= 0:
            return
        if t > 0:
            run = min(dt, t)  # antes del disparo nadie avanza
            self.v += self.rng.normal(0, self.v_walk * np.sqrt(run), self.n)
            self.v = np.clip(self.v, 3.0, 10.0)
            self.x += self.v * run + self.rng.normal(0, self.x_walk * np.sqrt(run), self.n)
            np.clip(self.x, 0, self.distance, out=self.x)
        self.t = t

    def on_cut(self, p_same: float = 0.95, p_back: float = 0.04, jitter: float = 6.0) -> None:
        """Cambio de plano: lo normal es que la nueva cámara siga mostrando la cabeza (cerca de
        donde estaba); a veces muestra al pelotón de atrás; rara vez otra cosa."""
        u = self.rng.random(self.n)
        same, back = u < p_same, (u >= p_same) & (u < p_same + p_back)
        anyw = ~(same | back)
        self.x[same] += self.rng.normal(0, jitter, same.sum())
        self.x[back] -= self.rng.uniform(0, 40.0, back.sum())
        half_lap = self.track.lap / 2
        self.x[anyw] += self.rng.uniform(-half_lap, half_lap, anyw.sum())
        np.clip(self.x, 0, self.distance, out=self.x)

    def update(self, likelihood: Likelihood) -> None:
        lik = np.asarray(likelihood(self.s), dtype=float)
        w = self.w * lik
        if w.sum() <= 0:  # evidencia incompatible con todo: se ignora
            return
        self.w = w / w.sum()
        if 1.0 / np.sum(self.w**2) < self.n / 2:
            self._resample()

    def _resample(self) -> None:
        idx = self.rng.choice(self.n, self.n, p=self.w)
        self.x, self.v = self.x[idx], self.v[idx]
        self.w = np.full(self.n, 1.0 / self.n)

    @property
    def s(self) -> np.ndarray:
        return np.mod(self.s0 + self.x, self.track.lap)

    def zone_probs(self) -> np.ndarray:
        return np.bincount(zone_of(self.s, self.track) - 1, weights=self.w, minlength=6)

    def estimate(self) -> dict:
        p = self.zone_probs()
        order = np.argsort(self.x)
        cw = np.cumsum(self.w[order])
        xs = self.x[order]
        # cuantiles robustos: unas pocas partículas sueltas no inflan la dispersión
        q16 = xs[np.searchsorted(cw, 0.16)]
        q84 = xs[min(np.searchsorted(cw, 0.84), self.n - 1)]
        x = float(xs[min(np.searchsorted(cw, 0.5), self.n - 1)])
        return {
            "zone": int(np.argmax(p)) + 1,
            "p": [round(float(q), 3) for q in p],
            "s": round(float((self.s0 + x) % self.track.lap), 1),
            "x": round(x, 1),
            "x_std": round(float(q84 - q16) / 2, 1),
            "v": round(float(np.sum(self.w * self.v)), 2),
        }


class ZoneReporter:
    """Histéresis: la zona reportada solo cambia cuando otra supera `p_min` o le gana a la actual
    por `margin`, `hold` pasos seguidos. Evita el parpadeo en los límites entre zonas."""

    def __init__(self, p_min: float = 0.6, margin: float = 0.15, hold: int = 3) -> None:
        self.p_min, self.margin, self.hold = p_min, margin, hold
        self.zone: int | None = None
        self._cand: int | None = None
        self._count = 0

    def __call__(self, probs: np.ndarray) -> int:
        z = int(np.argmax(probs)) + 1
        if self.zone is None:
            self.zone = z
        elif z != self.zone and (
            probs[z - 1] >= self.p_min or probs[z - 1] - probs[self.zone - 1] >= self.margin
        ):
            self._count = self._count + 1 if z == self._cand else 1
            self._cand = z
            if self._count >= self.hold:
                self.zone, self._count = z, 0
        else:
            self._cand, self._count = None, 0
        return self.zone
