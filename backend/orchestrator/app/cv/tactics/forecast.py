"""Pronóstico del final de la carrera, causal (solo presente y pasado).

Entrada en cada instante: por atleta, metros recorridos desde la salida (`x`), velocidad (`v`) y
su incertidumbre (`sigma_x`). Salida: tiempo de llegada estimado de cada uno con intervalo,
P(ganar), P(podio), puesto esperado y el tiempo ganador.

Modelo del resto de la carrera (lo que falta, `r` metros) en dos tramos:

    ┌──────── crucero: r − K metros ────────┐┌──── sprint: K metros ────┐
     v vuelve hacia el nivel del campo          v = v_sprint
     (reversión a la media, escala λ)          (prior por nivel; en vivo, lo medido)

- **Nivel del campo** `v_lvl`: velocidad media plausible de la prueba (`PACE`), no el tiempo real
  de la carrera analizada. Si se conoce la marca de un atleta (`priors`), se usa la suya.
- **Crucero**: en una final táctica el ritmo actual no se mantiene: se acerca al nivel con escala
  λ metros. La media en `D` metros de `v(x) = v_lvl + (v0 − v_lvl)·e^(−x/λ)` es
  `v_lvl + (v0 − v_lvl)·λ/D·(1 − e^(−D/λ))`.
- **Sprint**: los últimos K metros (aleatorio) a `v_lvl · ratio`. Ya dentro del sprint, lo medido
  pesa cada vez más (traspaso lineal hasta la meta).
- **Monte Carlo con factores comunes**: el ritmo y el sprint del grupo, y el error de posición del
  grupo (filtro de zonas), son compartidos; encima van diferencias individuales. Así las
  probabilidades de puesto no confunden "todos más lentos" con "uno más lento".

Es un modelo con parámetros supuestos, no una medición: lo que sale es un pronóstico.
"""

from dataclasses import dataclass, field

import numpy as np

from app.cv.zones.layout import DEFAULT_PACE, PACE


@dataclass
class ForecastConfig:
    distance: float = 1500.0
    tau_pace: float = 8.0  # s, memoria de la velocidad actual (EWMA)
    level: tuple[float, float] | None = None  # (media, desv.) m/s del campo; None -> PACE
    level_ind_sd: float = 0.08  # m/s, diferencias de nivel entre atletas sin marca conocida
    revert_m: tuple[float, float] = (350.0, 100.0)  # λ: metros para acercarse al nivel
    kick_len: tuple[float, float] = (300.0, 70.0)  # K: metros finales de sprint
    kick_ratio: tuple[float, float] = (1.10, 0.04)  # v_sprint / v_lvl (grupo)
    kick_ind_sd: float = 0.15  # m/s, diferencias individuales en el sprint
    pos_common_sd: float = 6.0  # m, error de posición compartido (grupo)
    n_sims: int = 3000
    stale_s: float = 15.0  # s sin datos -> el atleta no entra al pronóstico

    def level_prior(self) -> tuple[float, float]:
        if self.level is not None:
            return self.level
        lo, hi = PACE.get(int(self.distance), DEFAULT_PACE)
        return (lo + hi) / 2, (hi - lo) / 4


@dataclass
class _Track:
    x: float
    v: float
    t: float
    sigma_x: float = 0.5
    finished_t: float | None = None


def cruise_mean_speed(v0, v_lvl, dist, lam):
    """Velocidad media en `dist` metros si v se acerca a v_lvl con escala lam (vectorizado)."""
    dist = np.maximum(dist, 1e-6)
    f = lam / dist * (1 - np.exp(-dist / lam))
    return v_lvl + (v0 - v_lvl) * f


@dataclass
class FinishForecaster:
    cfg: ForecastConfig = field(default_factory=ForecastConfig)
    priors: dict = field(default_factory=dict)  # id -> tiempo esperado (s) en la distancia
    seed: int = 0

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.tracks: dict[int, _Track] = {}

    def observe(self, t: float, athletes: list[dict]) -> None:
        dist = self.cfg.distance
        for a in athletes:
            i, x, v = a["id"], float(a["x"]), float(a["v"])
            tr = self.tracks.get(i)
            if tr is None:
                self.tracks[i] = tr = _Track(x=x, v=v, t=t)
            else:
                dt = max(t - tr.t, 0.0)
                w = 1 - np.exp(-dt / self.cfg.tau_pace)
                if tr.finished_t is None and x >= dist and tr.x < dist:  # cruce de meta interpolado
                    tr.finished_t = tr.t + (dist - tr.x) / max(x - tr.x, 1e-6) * dt
                tr.v += w * (v - tr.v)
                tr.x, tr.t = x, t
            tr.sigma_x = float(a.get("sigma_x", 0.5))
            if tr.finished_t is None and x >= dist:  # primera observación ya pasada la meta
                tr.finished_t = t

    def active(self, t: float) -> list[int]:
        return [
            i
            for i, tr in self.tracks.items()
            if tr.finished_t is not None or t - tr.t <= self.cfg.stale_s
        ]

    def forecast(self, t: float, ids: list[int] | None = None) -> dict:
        c, rng, n_sims = self.cfg, self.rng, self.cfg.n_sims
        ids = list(self.active(t) if ids is None else ids)
        if not ids:
            return {"t": t, "athletes": [], "winner": None}
        n = len(ids)
        trs = [self.tracks[i] for i in ids]
        mu_l, sd_l = c.level_prior()

        # nivel de cada atleta: marca conocida o el del campo
        lvl_mu = np.array([c.distance / self.priors[i] if i in self.priors else mu_l for i in ids])
        lvl_sd_ind = np.array([0.05 if i in self.priors else c.level_ind_sd for i in ids])

        # factores comunes (N,1) e individuales (N,n)
        z_lvl = rng.normal(0, sd_l, (n_sims, 1))
        lvl = lvl_mu + z_lvl + rng.normal(0, 1, (n_sims, n)) * lvl_sd_ind
        lam = np.clip(rng.normal(*c.revert_m, (n_sims, 1)), 100, 800)
        kick = np.clip(rng.normal(*c.kick_len, (n_sims, 1)), 120, 500)
        ratio = rng.normal(*c.kick_ratio, (n_sims, 1))
        v_kick = lvl * ratio + rng.normal(0, c.kick_ind_sd, (n_sims, n))

        # posición ahora: extrapolada desde la última observación + errores
        x0 = np.array([tr.x + tr.v * (t - tr.t) for tr in trs])
        v0 = np.array([tr.v for tr in trs])
        sx = np.array([tr.sigma_x for tr in trs])
        x = x0 + rng.normal(0, c.pos_common_sd, (n_sims, 1)) + rng.normal(0, 1, (n_sims, n)) * sx
        r = np.maximum(c.distance - x, 0.0)

        pre = np.maximum(r - kick, 0.0)
        kick_d = np.minimum(r, kick)
        v_pre = np.maximum(cruise_mean_speed(v0, lvl, pre, lam), 3.0)
        # dentro del sprint, lo medido manda cada vez más (alpha: 0 al entrar, 1 en la meta)
        alpha = np.where(r < kick, 1 - r / kick, 0.0)
        v_k = np.maximum((1 - alpha) * v_kick + alpha * np.maximum(v0, 0.5 * v_kick), 3.0)
        total = t + pre / v_pre + kick_d / v_k

        done = np.array([tr.finished_t is not None for tr in trs])
        if done.any():
            total[:, done] = [tr.finished_t for tr, d in zip(trs, done, strict=True) if d]

        rank = total.argsort(1).argsort(1) + 1  # 1 = gana
        q = np.percentile(total, [10, 50, 90], axis=0)
        win_t = total.min(1)
        out = [
            {
                "id": i,
                "x": round(float(x0[k]), 1),
                "v": round(float(v0[k]), 2),
                "eta": [round(float(q[j, k]), 1) for j in range(3)],
                "p_win": round(float((rank[:, k] == 1).mean()), 3),
                "p_podium": round(float((rank[:, k] <= 3).mean()), 3),
                "exp_rank": round(float(rank[:, k].mean()), 2),
            }
            for k, i in enumerate(ids)
        ]
        out.sort(key=lambda a: a["exp_rank"])
        return {
            "t": round(t, 3),
            "athletes": out,
            "winner": [round(float(v), 1) for v in np.percentile(win_t, [10, 50, 90])],
        }

    def update(self, t: float, athletes: list[dict]) -> dict:
        self.observe(t, athletes)
        return self.forecast(t)
