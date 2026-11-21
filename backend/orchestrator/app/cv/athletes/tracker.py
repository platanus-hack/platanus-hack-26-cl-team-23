"""Estado por atleta: posición y velocidad respecto a la cancha = grupo + relativo al grupo.

Kalman por atleta sobre (x, u) longitudinal y d lateral:
    predicción:  x += (v_grupo + u)·dt     u se relaja a 0 (nadie sostiene una ventaja eterna)
    medición:    x = Δs_medido + ancla común;  d = metros al bordillo
El ancla común sale de los atletas ya seguidos en el plano (así, si el de adelante se tapa, no
se mueven todos) y el grupo (filtro de zonas: la cabeza de carrera) la corrige despacio. Esa
corrección traslada a todos por igual y NO entra en u: si no, cada salto del filtro de grupo se
leería como un sprint.

Tras un corte cambian las identidades del tracker de imagen: se re-asignan por posición predicha
+ color de camiseta, y nunca hay más atletas que corredores en la serie.
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Athlete:
    id: int
    x: float  # metros recorridos desde la salida (sin envolver)
    u: float  # velocidad relativa al grupo (m/s)
    d: float  # metros al bordillo
    P: np.ndarray  # covarianza de (x, u)
    Pd: float  # varianza de d
    app: np.ndarray | None  # color de camiseta
    last_t: float
    seen: int = 1
    tid: int | None = None
    box: tuple | None = None


def _assign(cost: np.ndarray, limit: float = 1e5) -> list[tuple[int, int]]:
    """Asignación codiciosa por costo creciente (con ≤ 12 atletas basta; evita depender de scipy)."""
    pairs = sorted(
        (cost[r, c], r, c)
        for r in range(cost.shape[0])
        for c in range(cost.shape[1])
        if cost[r, c] < limit
    )
    used_r, used_c, out = set(), set(), []
    for _, r, c in pairs:
        if r not in used_r and c not in used_c:
            used_r.add(r)
            used_c.add(c)
            out.append((r, c))
    return out


class AthleteTracker:
    def __init__(
        self,
        field_size: int | None = 12,
        q_u: float = 0.1,
        tau_u: float = 15.0,
        gate_m: float = 6.0,
        w_app: float = 6.0,
        max_app: float = 0.9,
        beta: float = 0.03,
        forget_s: float = 40.0,
    ) -> None:
        self.field_size, self.q_u, self.tau_u = field_size, q_u, tau_u
        self.gate_m, self.w_app, self.max_app = gate_m, w_app, max_app
        self.beta, self.forget_s = beta, forget_s
        self.ath: dict[int, Athlete] = {}
        self.alias: dict[int, int] = {}  # id del tracker de imagen -> id de atleta
        self.next_id = 0
        self.offset: float | None = None
        self.t: float | None = None

    def predict(self, t: float, v_group: float) -> None:
        if self.t is None:
            self.t = t
            return
        dt = t - self.t
        if dt <= 0:
            return
        r = math.exp(-dt / self.tau_u)
        F = np.array([[1, dt], [0, r]])
        Q = np.array([[0.05 * dt, 0], [0, self.q_u**2 * dt]])
        for a in self.ath.values():
            a.x += (v_group + a.u) * dt
            a.u *= r
            a.P = F @ a.P @ F.T + Q
            a.Pd += 0.02 * dt
        self.t = t

    def update(self, t, x_group, meas, tids, apps, cut=False) -> list[Athlete]:
        """meas: dicts de measure_frame con `ds` ya en el sentido "adelante" (sigma_ds ≥ 1e5 si no
        se sabe el sentido); tids: id del tracker de imagen por medición; apps: color de camiseta."""
        if not meas:
            self._forget(t)
            return []
        if cut:
            self.alias.clear()
            self.offset = None
        lead = max(m["ds"] for m in meas)
        ids: list[int | None] = [self.alias.get(int(k)) if k is not None else None for k in tids]
        seen: set[int] = set()
        for j, i in enumerate(ids):  # dos mediciones al mismo atleta: el tracker se confundió
            if i is not None and i in seen:
                ids[j] = None
            if i is not None:
                seen.add(i)

        known = [
            self.ath[i].x - meas[j]["ds"]
            for j, i in enumerate(ids)
            if i is not None and i in self.ath
        ]
        group_off, shift = x_group - lead, 0.0
        if known and self.offset is not None:
            self.offset = float(np.median(known))
            shift = self.beta * (group_off - self.offset)
        else:
            self.offset = group_off
        z = [m["ds"] + self.offset for m in meas]

        taken = {i for i in ids if i is not None}
        free = [a for a in self.ath.values() if a.id not in taken]
        new = [j for j, i in enumerate(ids) if i is None]
        if new and free:
            cost = np.full((len(new), len(free)), 1e6)
            for r, j in enumerate(new):
                for c, a in enumerate(free):
                    gap = abs(z[j] - a.x)
                    da = (
                        0.0
                        if apps[j] is None or a.app is None
                        else float(np.linalg.norm(apps[j] - a.app))
                    )
                    if gap > self.gate_m + 3 * math.sqrt(a.P[0, 0]) or da > self.max_app:
                        continue
                    dz = gap / math.sqrt(a.P[0, 0] + min(meas[j]["sigma_ds"], 30.0) ** 2 + 4.0)
                    dd = (
                        0.0
                        if meas[j]["d"] is None
                        else abs(meas[j]["d"] - a.d) / math.sqrt(a.Pd + 0.5)
                    )
                    cost[r, c] = dz + 0.5 * dd + self.w_app * da
            for r, c in _assign(cost):
                ids[new[r]] = free[c].id
            # serie completa: los que siguen sin asignar son conocidos; se asignan sin compuertas
            rest = [r for r in range(len(new)) if ids[new[r]] is None]
            used = {i for i in ids if i is not None}
            ghosts = [c for c, a in enumerate(free) if a.id not in used]
            if self.field_size and rest and ghosts and len(self.ath) >= self.field_size:
                cost2 = np.zeros((len(rest), len(ghosts)))
                for ri, r in enumerate(rest):
                    j = new[r]
                    for gi, c in enumerate(ghosts):
                        a = free[c]
                        da = (
                            1.0
                            if apps[j] is None or a.app is None
                            else float(np.linalg.norm(apps[j] - a.app))
                        )
                        cost2[ri, gi] = abs(z[j] - a.x) / 10 + self.w_app * da
                for ri, gi in _assign(cost2):
                    ids[new[rest[ri]]] = free[ghosts[gi]].id

        out = []
        for j, m in enumerate(meas):
            if ids[j] is None:
                self.next_id += 1
                has_d = m["d"] is not None
                a = Athlete(
                    self.next_id,
                    z[j],
                    0.0,
                    float(np.clip(m["d"], 0, 11)) if has_d else 1.0,
                    np.diag([min(m["sigma_ds"], 30.0) ** 2 + 1.0, 0.5]),
                    m["sigma_d"] ** 2 if has_d else 4.0,
                    apps[j],
                    t,
                )
                self.ath[a.id] = a
                ids[j] = a.id
            else:
                a = self.ath[ids[j]]
                R = m["sigma_ds"] ** 2
                innov = z[j] - a.x
                if R >= 1e5:  # sin sentido "adelante" conocido: no informa
                    innov, R = 0.0, 1e6
                if innov**2 > 16 * (a.P[0, 0] + R):  # atípico: cuenta, pero con poco peso
                    R *= innov**2 / (16 * (a.P[0, 0] + R))
                S = a.P[0, 0] + R
                K = a.P[:, 0] / S
                a.x += K[0] * innov
                a.u += K[1] * innov
                a.P = a.P - np.outer(K, a.P[0, :])
                if m["d"] is not None:
                    Rd = m["sigma_d"] ** 2
                    if (m["d"] - a.d) ** 2 > 9 * (a.Pd + Rd):
                        Rd *= (m["d"] - a.d) ** 2 / (9 * (a.Pd + Rd))
                    kd = a.Pd / (a.Pd + Rd)
                    a.d = float(np.clip(a.d + kd * (m["d"] - a.d), 0.0, 11.0))
                    a.Pd *= 1 - kd
                if apps[j] is not None:
                    a.app = apps[j] if a.app is None else 0.9 * a.app + 0.1 * apps[j]
                a.seen += 1
            a = self.ath[ids[j]]
            a.last_t, a.tid = t, tids[j]
            a.box = m.get("bbox")
            if tids[j] is not None:
                self.alias[int(tids[j])] = a.id
            out.append(a)
        if shift:
            for a in self.ath.values():
                a.x += shift
            self.offset += shift
        self._forget(t)
        return out

    def _forget(self, t: float) -> None:
        for k in [k for k, a in self.ath.items() if t - a.last_t > self.forget_s]:
            del self.ath[k]
        alive = set(self.ath)
        self.alias = {k: v for k, v in self.alias.items() if v in alive}


def stable_order(
    athletes: list[Athlete], prev_ids: list[int], margin: float = 0.4
) -> list[Athlete]:
    """Orden por metros recorridos con histéresis: dos atletas solo cambian de puesto si la
    diferencia supera `margin` (en un grupo apretado el ruido de ±0,5 m invertiría el orden a
    cada frame)."""
    pos = {i: k for k, i in enumerate(prev_ids)}
    order = sorted(athletes, key=lambda q: (pos.get(q.id, len(pos)), -q.x))
    changed = True
    while changed:
        changed = False
        for k in range(len(order) - 1):
            a, b = order[k], order[k + 1]
            if b.x > a.x + (0.0 if b.id not in pos else margin):
                order[k], order[k + 1] = b, a
                changed = True
    return order
