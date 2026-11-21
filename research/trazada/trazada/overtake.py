"""Recomendador de adelantamiento: ¿cuándo le conviene a un atleta atacar al de adelante?

Modelo de energía de velocidad crítica (CS, D′), el estándar en medio fondo:
- Por encima de CS se gasta la reserva D′ (en metros): `dD′ = −(v − CS)·dt`; por debajo se
  recarga más lento (`recover`). Con reserva E, lo más rápido que se cubren r metros es
  `T = max((r − E)/CS, r/v_pico)`: o se acaba la energía, o se llega al tope de velocidad.
- **Rebufo**: ir 0,3–2 m detrás de otro, en la misma línea, cuesta como correr un `draft`
  (3 %) más lento.
- **Curva**: pasar por fuera en curva suma metros (`Track.extra_distance_rate`); en recta, no.

Las capacidades de cada atleta (nivel, D′, v_pico) son inciertas: partículas con un prior
del campo. La reserva de cada partícula se integra en vivo con la velocidad medida (y el rebufo
detectado); si una partícula dice "sin energía" pero el atleta sigue rápido, pierde peso. Así se
aprende en carrera quién viene más entero.

Duelo A (atacante) vs B (el de adelante) para cada punto de ataque `a` (metros que le faltan a B):
  1. Crucero hasta `a`: ambos al ritmo del grupo (reversión al nivel, como en forecast.py).
     A gana rebufo si va pegado.
  2. Desde `a`, sprint a fondo los dos. A corre `a + gap + metros extra por ir por fuera`; ahora
     es B quien va a rebufo.
  P(A llega antes que B) por punto de ataque -> se recomienda el mejor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .forecast import ForecastConfig, cruise_mean_speed
from .geometry import STANDARD, Track
from .zones import NAMES, start_s, zone_of


@dataclass
class OvertakeConfig:
    distance: float = 1500.0
    dprime: tuple[float, float] = (180.0, 40.0)   # m, reserva anaeróbica D′
    v_peak: tuple[float, float] = (8.6, 0.3)      # m/s, velocidad tope de sprint
    level_ind_sd: float = 0.10                    # m/s, nivel de cada atleta alrededor del campo
    draft: float = 0.03                           # ahorro relativo yendo a rebufo
    draft_box: tuple[float, float, float] = (0.3, 2.0, 0.7)   # m detrás (min, max), |Δd| máx
    recover: float = 0.5                          # recarga de D′ por debajo de CS (fracción)
    pass_offset: float = 1.0                      # m hacia afuera para pasar
    pass_len: float = 25.0                        # m que dura la maniobra
    revert_m: float = 350.0                       # λ del crucero (igual que forecast)
    deficit_scale: float = 30.0                   # m·s de "energía negativa" que cuestan 1 nat
    step: float = 25.0                            # resolución de puntos de ataque
    min_attack: float = 50.0
    max_gap: float = 15.0                         # más lejos no es un duelo
    n: int = 1000
    stale_s: float = 15.0


@dataclass
class _Athlete:
    cs: np.ndarray
    d0: np.ndarray
    vp: np.ndarray
    E: np.ndarray
    logw: np.ndarray
    t: float
    x: float = 0.0
    d: float = 0.0
    v: float = 0.0
    draft_m: float = 0.0          # metros recorridos a rebufo
    drafting: bool = False


def best_time(r, E, cs, vp):
    """Tiempo mínimo para r metros con reserva E (modelo CS–D′ con tope de velocidad)."""
    E = np.maximum(E, 0.0)
    return np.maximum((r - E) / cs, r / vp)


def pass_extra(a_togo, d_rival, cfg: OvertakeConfig, distance: float, track: Track = STANDARD):
    """Metros extra por pasar por fuera, empezando cuando al rival le faltan `a_togo` m."""
    s0 = start_s(distance, track)
    s = (s0 + distance - a_togo + np.arange(0, cfg.pass_len, 1.0)) % track.lap
    rate_out = np.array([track.extra_distance_rate(si, d_rival + cfg.pass_offset) for si in s])
    rate_in = np.array([track.extra_distance_rate(si, d_rival) for si in s])
    return float((rate_out - rate_in).sum())


def where(a_togo, distance, track: Track = STANDARD) -> str:
    s = (start_s(distance, track) + distance - a_togo) % track.lap
    return NAMES[zone_of(s, track)]


@dataclass
class OvertakeAdvisor:
    cfg: OvertakeConfig = field(default_factory=OvertakeConfig)
    fcfg: ForecastConfig = field(default_factory=ForecastConfig)
    priors: dict = field(default_factory=dict)        # id -> marca (s) en la distancia
    seed: int = 0

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        self.ath: dict = {}

    # --- partículas -------------------------------------------------------------------------
    def _new(self, i, t, params=None) -> _Athlete:
        c, N, rng = self.cfg, self.cfg.n, self.rng
        if params is not None:      # capacidades conocidas (tests / atletas medidos)
            cs, d0, vp = (np.full(N, float(params[k])) for k in ("cs", "dprime", "v_peak"))
        else:
            mu_l, sd_l = self.fcfg.level_prior()
            lvl = (c.distance / self.priors[i] + rng.normal(0, 0.05, N)) if i in self.priors \
                else rng.normal(mu_l, np.hypot(sd_l, c.level_ind_sd), N)
            d0 = np.clip(rng.normal(*c.dprime, N), 60, 400)
            cs = (c.distance - d0) / (c.distance / lvl)       # marca = (D − D′)/CS
            vp = np.maximum(rng.normal(*c.v_peak, N), cs + 1.0)
        return _Athlete(cs=cs, d0=d0, vp=vp, E=d0.copy(), logw=np.zeros(N), t=t)

    def set_params(self, i, t, cs, dprime, v_peak):
        self.ath[i] = self._new(i, t, {"cs": cs, "dprime": dprime, "v_peak": v_peak})

    def _drafting(self, a, others) -> bool:
        lo, hi, lat = self.cfg.draft_box
        return any(lo <= o["x"] - a["x"] <= hi and abs(o.get("d", 0) - a.get("d", 0)) <= lat
                   for o in others if o["id"] != a["id"])

    def observe(self, t: float, athletes: list[dict]):
        c = self.cfg
        for a in athletes:
            st = self.ath.get(a["id"])
            if st is None:
                st = self.ath[a["id"]] = self._new(a["id"], t)
                st.x, st.v, st.t = float(a["x"]), float(a["v"]), t
            dt = max(t - st.t, 0.0)
            st.drafting = self._drafting(a, athletes)
            v = max(float(a["v"]), 0.0)
            if dt > 0:
                v_cost = v * (1 - c.draft * st.drafting)
                burn = v_cost - st.cs
                st.E = np.minimum(st.E - np.where(burn > 0, burn, c.recover * burn) * dt, st.d0)
                # sigue corriendo rápido con reserva negativa -> esa partícula es poco creíble
                st.logw -= np.maximum(-st.E, 0) / c.deficit_scale * dt
                st.logw -= st.logw.max()
                st.draft_m += v * dt * st.drafting
            st.x, st.d, st.v, st.t = float(a["x"]), float(a.get("d", 0.0)), v, t

    def _sample(self, st: _Athlete, N):
        w = np.exp(st.logw - st.logw.max())
        idx = self.rng.choice(len(w), N, p=w / w.sum())
        return st.cs[idx], st.d0[idx], st.vp[idx], np.maximum(st.E[idx], 0.0)

    # --- decisión ---------------------------------------------------------------------------
    def rival_ahead(self, i, t):
        me = self.ath[i]
        cands = [(o.x - me.x, j) for j, o in self.ath.items()
                 if j != i and t - o.t <= self.cfg.stale_s and 0 < o.x - me.x <= self.cfg.max_gap]
        return min(cands)[1] if cands else None

    def duel(self, i, j, t) -> dict:
        """P(i llega antes que j) para cada punto de ataque (metros que le faltan a j)."""
        c, N = self.cfg, self.cfg.n
        A, B = self.ath[i], self.ath[j]
        gap = B.x - A.x
        rB = c.distance - B.x
        csA, d0A, vpA, EA = self._sample(A, N)
        csB, d0B, vpB, EB = self._sample(B, N)
        mu_l = self.fcfg.level_prior()[0]
        drafting_now = c.draft_box[0] <= gap <= c.draft_box[1]

        a_list = [rB] + [a for a in np.arange(np.floor(rB / c.step) * c.step, c.min_attack - 1e-9, -c.step)
                         if a < rB - 1e-6]
        out = []
        for a in a_list:
            cruise = rB - a
            vc = float(cruise_mean_speed(B.v, mu_l, cruise, c.revert_m)) if cruise > 0 else B.v
            def after_cruise(E, cs, d0, draft):
                burn = vc * (1 - c.draft * draft) - cs
                dt = cruise / max(vc, 1e-6)
                return np.minimum(E - np.where(burn > 0, burn, c.recover * burn) * dt, d0)
            EA_a = after_cruise(EA, csA, d0A, drafting_now)
            EB_a = after_cruise(EB, csB, d0B, False)
            extra = pass_extra(a, B.d, c, c.distance)
            dA = a + gap + extra
            EB_s = EB_a + c.draft * max(a - c.pass_len, 0)      # ahora B va a rebufo de A
            TA = best_time(dA, EA_a, csA, vpA)
            TB = best_time(a, EB_s, csB, vpB)
            out.append({"a": round(float(a), 1), "p": float((TA < TB).mean()), "extra": round(extra, 2),
                        "zone": where(a, c.distance)})
        return {"gap": round(gap, 2), "r": round(rB, 1), "curve": out,
                "E_A": float(np.median(EA / d0A)), "E_B": float(np.median(EB / d0B))}

    def recommend(self, i, t) -> dict:
        j = self.rival_ahead(i, t)
        if j is None:
            return {"id": i, "action": "sin rival cerca", "rival": None}
        d = self.duel(i, j, t)
        curve = d["curve"]
        k_best = int(np.argmax([e["p"] for e in curve]))
        best, now = curve[k_best], curve[0]
        # ventana: puntos contiguos al mejor que no pierden más de `tol`
        tol = 0.03
        lo = hi = k_best
        while lo > 0 and curve[lo - 1]["p"] >= best["p"] - tol:
            lo -= 1
        while hi < len(curve) - 1 and curve[hi + 1]["p"] >= best["p"] - tol:
            hi += 1
        window = (curve[lo]["a"], curve[hi]["a"])           # (desde, hasta) en metros que faltan
        if best["p"] < 0.25:
            action, at = "MANTENER a rebufo: no hay ventana", best
        elif lo == 0:
            action, at = f"ATACAR: ventana abierta hasta {window[1]:.0f} m", now
        else:
            at = curve[(lo + hi) // 2]
            action = f"ESPERAR: ventana {window[0]:.0f}–{window[1]:.0f} m, ideal {at['a']:.0f} m"
        why = [f"reserva {d['E_A']:.0%} vs rival {d['E_B']:.0%}",
               f"{self.ath[i].draft_m:.0f} m a rebufo"]
        if at["extra"] > 0.3:
            why.append(f"pasar ahí cuesta {at['extra']:.1f} m extra (curva)")
        return {"id": i, "rival": j, "action": action, "p_attack": round(at["p"], 3),
                "p_now": round(now["p"], 3), "at_m": at["a"], "zone": at["zone"], "gap": d["gap"],
                "window": window,
                "why": "; ".join(why), "curve": [(e["a"], round(e["p"], 3)) for e in curve]}
