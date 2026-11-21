"""Filtro causal de "en qué zona de la pista está enfocando la cámara".

Estado (por partícula): x = metros recorridos desde la salida por el punto que enfoca la cámara
(sin envolver), y v = velocidad a la que avanza ese punto. La zona sale de s = salida + x.

Por qué partículas sobre una posición continua y no un HMM de 6 estados: el orden
1 -> 2 -> ... -> 6 y cuánto dura cada zona salen solos de `x += v·dt`, sin modelar transiciones.

Pasos (solo usa el presente y el pasado):
  predict(t)       avanza hasta el tiempo de carrera t (del reloj de TV o del inicio conocido)
  on_cut()         la cámara cambió de plano: el foco puede moverse, la carrera no
  update(lik)      evidencia visual: lik(s) -> verosimilitud por partícula (aún no se usa)
  zone_probs()     P(Z1..Z6)
"""
from __future__ import annotations

import numpy as np

from .geometry import STANDARD, Track
from .zones import PACE, start_s, zone_of


class ZoneFilter:
    def __init__(self, distance: float = 1500, track: Track = STANDARD, n: int = 4000,
                 pace: tuple[float, float] | None = None, v_walk: float = 0.04,
                 x_walk: float = 0.3, seed: int = 0):
        self.track, self.distance = track, distance
        self.s0 = start_s(distance, track)
        self.rng = np.random.default_rng(seed)
        lo, hi = pace or PACE.get(int(distance), (5.5, 8.0))
        self.n = n
        self.x = np.zeros(n)
        self.v = self.rng.uniform(lo, hi, n)
        self.w = np.full(n, 1.0 / n)
        self.v_walk = v_walk      # m/s por √s: el ritmo cambia despacio (tirones, remate)
        self.x_walk = x_walk      # m por √s: la cámara no sigue exactamente al líder
        self.t = 0.0

    # ------------------------------------------------------------------ predicción
    def predict(self, t: float):
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

    def on_cut(self, p_same: float = 0.95, p_back: float = 0.04, jitter: float = 6.0):
        """Cambio de plano. Lo normal es que la nueva cámara siga mostrando la cabeza de carrera
        (cerca de donde estaba); a veces muestra al pelotón de atrás; rara vez otra cosa.
        En la final del 1500 los 14 cortes mantienen a la cabeza en cuadro: un corte NO es un
        cambio de zona. Un modelo más pesimista (15 % fuera) dejaba partículas sueltas que la
        evidencia ambigua terminaba eligiendo."""
        u = self.rng.random(self.n)
        same, back = u < p_same, (u >= p_same) & (u < p_same + p_back)
        anyw = ~(same | back)
        self.x[same] += self.rng.normal(0, jitter, same.sum())
        self.x[back] -= self.rng.uniform(0, 40.0, back.sum())
        self.x[anyw] += self.rng.uniform(-self.track.lap / 2, self.track.lap / 2, anyw.sum())
        np.clip(self.x, 0, self.distance, out=self.x)

    # ------------------------------------------------------------------ evidencia
    def update(self, likelihood):
        """likelihood: función s (array) -> verosimilitud >= 0 por partícula."""
        lik = np.asarray(likelihood(self.s), dtype=float)
        w = self.w * lik
        if w.sum() <= 0:          # evidencia incompatible con todo: se ignora
            return
        self.w = w / w.sum()
        if 1.0 / np.sum(self.w ** 2) < self.n / 2:
            self._resample()

    def update_x(self, x_obs: float, sigma: float = 3.0):
        """Observación directa de los metros recorridos (p. ej. paso por la meta). Las partículas
        cuya velocidad las dejó en el lugar correcto sobreviven: así se aprende también el ritmo."""
        lik = np.exp(-0.5 * ((self.x - x_obs) / sigma) ** 2)
        if (self.w * lik).sum() < 1e-12:      # todo lejos: se acerca la nube en vez de descartarla
            self.x += x_obs - float(np.sum(self.w * self.x))
            lik = np.exp(-0.5 * ((self.x - x_obs) / sigma) ** 2)
        self.w = self.w * lik
        self.w /= self.w.sum()
        self._resample()

    def update_v(self, v_obs: float, sigma: float = 0.8, inject: float = 0.0):
        """Medición directa de la velocidad (p. ej. contra marcas de la pista).

        `inject`: fracción de partículas que se re-sortean alrededor de la medición antes de
        pesar. Sin esto, si el ritmo sale del rango del prior (vuelta táctica a 5,6 m/s con un
        prior de 6,3–7,1) no hay partículas ahí y el filtro solo se arrastra de a poco."""
        if inject > 0:
            k = self.rng.random(self.n) < inject
            self.v[k] = self.rng.normal(v_obs, sigma, k.sum())
        lik = np.exp(-0.5 * ((self.v - v_obs) / sigma) ** 2)
        if (self.w * lik).sum() < 1e-12:      # todas lejos: se corre la nube hacia la medición
            self.v += 0.5 * (v_obs - float(np.sum(self.w * self.v)))
            lik = np.exp(-0.5 * ((self.v - v_obs) / sigma) ** 2)
        self.w = self.w * lik
        self.w /= self.w.sum()
        if 1.0 / np.sum(self.w ** 2) < self.n / 2:
            self._resample()
            self.v += self.rng.normal(0, 0.05, self.n)    # sin esto la nube de v colapsa

    def _resample(self):
        idx = self.rng.choice(self.n, self.n, p=self.w)
        self.x, self.v = self.x[idx], self.v[idx]
        self.w = np.full(self.n, 1.0 / self.n)

    # ------------------------------------------------------------------ salida
    @property
    def s(self) -> np.ndarray:
        return np.mod(self.s0 + self.x, self.track.lap)

    def zone_probs(self) -> np.ndarray:
        """P(Z1..Z6) como array de 6."""
        return np.bincount(zone_of(self.s, self.track) - 1, weights=self.w, minlength=6)

    def estimate(self) -> dict:
        p = self.zone_probs()
        x = float(np.sum(self.w * self.x))
        # dispersión robusta (cuantiles 16-84): unas pocas partículas sueltas no la inflan
        o = np.argsort(self.x)
        cw = np.cumsum(self.w[o])
        q16, q84 = self.x[o][np.searchsorted(cw, 0.16)], self.x[o][min(np.searchsorted(cw, 0.84), self.n - 1)]
        x = float(self.x[o][np.searchsorted(cw, 0.5)])   # mediana: robusta a modos lejanos
        return {"t": round(self.t, 3), "zone": int(np.argmax(p)) + 1, "p": [round(float(q), 3) for q in p],
                "s": round(float((self.s0 + x) % self.track.lap), 1), "x": round(x, 1),
                "x_std": round(float(q84 - q16) / 2, 1),
                "v": round(float(np.sum(self.w * self.v)), 2)}


class ZoneReporter:
    """Histéresis: solo cambia la zona reportada cuando otra zona supera `p_min`, o le gana a la
    actual por `margin`, durante `hold` pasos seguidos. Evita que la salida parpadee en los
    límites sin quedarse pegada cuando la incertidumbre crece y ninguna zona llega a `p_min`."""

    def __init__(self, p_min: float = 0.6, margin: float = 0.15, hold: int = 3):
        self.p_min, self.margin, self.hold = p_min, margin, hold
        self.zone, self._cand, self._count = None, None, 0

    def __call__(self, probs) -> int | None:
        z = int(np.argmax(probs)) + 1
        if self.zone is None:
            self.zone = z
        elif z != self.zone and (probs[z - 1] >= self.p_min or probs[z - 1] - probs[self.zone - 1] >= self.margin):
            self._count = self._count + 1 if z == self._cand else 1
            self._cand = z
            if self._count >= self.hold:
                self.zone, self._count = z, 0
        else:
            self._cand, self._count = None, 0
        return self.zone
