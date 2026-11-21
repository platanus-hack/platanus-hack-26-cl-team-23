"""Posición y velocidad de cada atleta respecto a la cancha, en video de TV.

Triangulación:
    posición atleta  = posición del grupo en la pista (filtro de zonas)
                     + posición del atleta relativa al grupo (medida dentro del mismo frame)
    velocidad atleta = velocidad del grupo + velocidad del atleta relativa al grupo

Lo relativo se mide dentro de un frame, así que no importa que la cámara panee o haga zoom.
Hacen falta dos reglas en la imagen:

  - Lateral (d, distancia al bordillo): las calles, 1,22 m. Desde los pies del atleta se recorre la
    imagen en dirección transversal a las líneas hasta el pasto (el bordillo de Hayward es una
    baranda elevada, el pasto empieza ahí) y se mide esa distancia en "calles", usando el
    espaciado local entre líneas. Las razones de distancias sobre una recta se conservan en
    perspectiva: no hace falta calibrar la cámara.
  - Longitudinal (Δs, quién va adelante y por cuánto): el cuerpo. La caja de un corredor mide
    ~1,75 m de alto (el ancho cambia ×3 con la zancada, el alto casi no): píxeles por metro donde
    está cada uno. Con la dirección local de las líneas (= dirección de carrera en la imagen) y el
    escorzo que delata el espaciado entre calles se arma un mapa local suelo -> imagen
    (perspectiva débil). De frente (la pista se aleja de la cámara) lo longitudinal es
    profundidad: solo se mide por el cambio de tamaño, con el orden seguro y la distancia
    aproximada.

Todo es causal: solo usa el frame actual y el estado acumulado.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .broadcast import line_mask

BODY_H = 1.75          # m: alto de la caja de un corredor en carrera
LANE = 1.22
IGNORE_TV = [(0, 645, 1280, 720), (990, 555, 1225, 645), (45, 28, 240, 66)]   # ticker, marcador, logo


def tartan_mask(hsv):
    h, s, v = cv2.split(hsv)
    return (((h < 14) | (h > 165)) & (s > 70) & (v > 60)).astype(np.uint8)


def grass_mask(hsv):
    h, s, v = cv2.split(hsv)
    return ((h > 33) & (h < 90) & (s > 50) & (v > 40)).astype(np.uint8)


# ------------------------------------------------------------------ ¿quién es corredor?
def select_runners(boxes: np.ndarray, hsv: np.ndarray, ignore=IGNORE_TV) -> np.ndarray:
    """Índices de cajas que son corredores: pies sobre tartán, tamaño parecido al del grupo,
    fuera de los gráficos de TV. Descarta público, jueces en el pasto y camarógrafos."""
    if len(boxes) == 0:
        return np.zeros(0, int)
    H, W = hsv.shape[:2]
    red = tartan_mask(hsv)
    ok = []
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        fx, fy = (x1 + x2) / 2, y2
        if any(a <= fx <= c and b <= fy <= d for a, b, c, d in ignore):
            continue
        h = y2 - y1
        r = max(3, int(0.08 * h))
        xa, xb = int(max(0, fx - 2 * r)), int(min(W, fx + 2 * r + 1))
        patch = red[int(max(0, fy - r)):int(min(H, fy + r + 1)), xa:xb]
        if patch.size and patch.mean() > 0.3:
            ok.append(i)
    ok = np.array(ok, int)
    if len(ok) >= 3:
        h = boxes[ok, 3] - boxes[ok, 1]
        med = np.median(h)
        ok = ok[(h > 0.35 * med) & (h < 2.2 * med)]
    return ok


# ------------------------------------------------------------------ medición en el frame
def local_direction(mask, foot, radius, exclude):
    """Orientación (rad, en [-π/2, π/2)) de las líneas pintadas cerca de un punto, con el tensor de
    estructura de la máscara de líneas en una ventana, sin cajas de corredores ni gráficos.
    -> (phi | None, coherencia 0..1)"""
    H, W = mask.shape
    x0, y0 = int(max(0, foot[0] - radius)), int(max(0, foot[1] - radius))
    x1, y1 = int(min(W, foot[0] + radius)), int(min(H, foot[1] + radius))
    sub = mask[y0:y1, x0:x1].copy()
    for (a, b, c, d) in exclude:
        sub[max(0, int(b) - y0):max(0, int(d) - y0), max(0, int(a) - x0):max(0, int(c) - x0)] = 0
    if sub.sum() < 40:
        return None, 0.0
    g = cv2.GaussianBlur(sub.astype(np.float32), (0, 0), 2.0)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    jxx, jyy, jxy = float((gx * gx).sum()), float((gy * gy).sum()), float((gx * gy).sum())
    theta = 0.5 * math.atan2(2 * jxy, jxx - jyy)          # dirección dominante del gradiente
    coh = math.hypot(jxx - jyy, 2 * jxy) / (jxx + jyy + 1e-9)
    phi = (theta + math.pi / 2 + math.pi / 2) % math.pi - math.pi / 2   # líneas ⟂ gradiente
    return phi, coh


def long_segments_direction(mask, top=0, min_len=90):
    """Orientación dominante de los segmentos largos de línea por debajo de `top` (o None)."""
    sub = mask[max(0, top):645]
    segs = cv2.HoughLinesP(sub * 255, 1, np.pi / 180, threshold=50, minLineLength=min_len, maxLineGap=20)
    if segs is None:
        return None
    segs = segs.reshape(-1, 4).astype(float)
    dx, dy = segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]
    L, ang = np.hypot(dx, dy), np.arctan2(dy, dx)
    return 0.5 * math.atan2(np.sum(L * np.sin(2 * ang)), np.sum(L * np.cos(2 * ang)))


def _crossings(m):
    out, k = [], 0
    while k < len(m):
        if m[k]:
            j = k
            while j + 1 < len(m) and m[j + 1]:
                j += 1
            out.append((k + j) / 2)
            k = j + 1
        else:
            k += 1
    return out


def lateral_measure(mask, grass, excl_mask, foot, phi, ppm, n_scans=5, red=None):
    """Distancia del pie al bordillo en metros, contando calles.

    Barridos paralelos, transversales a las líneas, desde el pie. En cada barrido se ubican los
    cruces con líneas; el espaciado entre cruces consecutivos da el ancho de calle en px (L). El
    bordillo es la última línea de la serie periódica (huecos ≈ L) del lado donde la serie se
    acaba antes: hacia afuera siguen las 8-9 calles; hacia adentro, tras el bordillo, viene tartán
    sin líneas o pasto. (El borde del pasto no sirve: a veces hay 2-3 m de tartán antes.)
    Las razones de distancia sobre una recta se conservan en perspectiva: no hace falta calibrar.
    -> dict(d | None, sigma_d, lane_px, lanes_out) o None."""
    H, W = mask.shape
    u = np.array([math.cos(phi), math.sin(phi)])
    n = np.array([-u[1], u[0]])
    max_px = int(np.clip(10 * LANE * ppm, 80, 600))
    ts = np.arange(-max_px, max_px + 1)
    scans = []
    gaps = []
    for k in range(n_scans):
        off = (k - n_scans // 2) * 0.5 * ppm
        p = foot + off * u
        xs = np.round(p[0] + ts * n[0]).astype(int)
        ys = np.round(p[1] + ts * n[1]).astype(int)
        inside = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
        m = np.zeros(len(ts), bool)
        e = np.ones(len(ts), bool)
        m[inside] = mask[ys[inside], xs[inside]] > 0
        e[inside] = excl_mask[ys[inside], xs[inside]]
        rd = np.zeros(len(ts), bool)
        if red is not None:
            rd[inside] = red[ys[inside], xs[inside]] > 0
        c = np.array(_crossings(m & ~e))
        for a_, b_ in zip(c[:-1], c[1:]):
            if not e[int(a_):int(b_) + 1].any():
                gaps.append(b_ - a_)
        scans.append((c - max_px, e, rd | m))
    gaps = np.sort(np.array(gaps))
    gaps = gaps[gaps > max(3.0, 0.02 * ppm * LANE)]
    if len(gaps) < 2:
        return None
    base = np.percentile(gaps, 25)
    L = float(np.median(gaps[gaps < 1.35 * base]))

    ends = {+1: [], -1: []}
    for c, e, ground in scans:
        for sign in (+1, -1):
            cs = np.sort(c[c * sign > -1.05 * L] * sign)     # desde la línea más cercana, aunque quede del otro lado del pie
            if len(cs) == 0 or cs[0] > 1.3 * L:
                continue
            last, steps = cs[0], 0
            for x in cs[1:]:
                g = x - last
                m_ = round(g / L)
                if m_ >= 1 and abs(g - m_ * L) < 0.25 * L * m_:
                    # hueco de 2+ calles solo si en medio hay una persona tapando
                    if m_ > 1:
                        a_, b_ = sorted((int(last * sign + max_px), int(x * sign + max_px)))
                        if not e[a_:b_].any():
                            break
                    last, steps = x, steps + m_
                elif g < 0.5 * L:
                    continue
                else:
                    break
            # la serie terminó: ¿termina de verdad (hay imagen y no hay persona) o se acabó el barrido?
            i_last = int(last * sign + max_px)
            beyond = int(i_last + sign * 1.6 * L)
            if not (0 <= beyond < len(ts)) or e[min(beyond, i_last):max(beyond, i_last)].mean() > 0.5:
                continue
            # ¿qué hay más allá de la última línea? tartán ~1 calle y luego nada -> esa línea es la
            # 1|2 y el bordillo (sin pintar o baranda) está en el borde del tartán
            run = 0
            j = i_last + sign * 2
            while 0 <= j < len(ts) and (ground[j] or e[j]):   # una persona no corta el tartán
                run += 1
                j += sign
            if 0.6 * L < run < 1.4 * L:
                ends[sign].append((last + run + 2, steps + 1))
            else:
                ends[sign].append((last, steps))
    cand = {s_: np.median([x for x, _ in v]) for s_, v in ends.items() if len(v) >= max(2, n_scans // 2)}
    if not cand:
        return {"d": None, "sigma_d": None, "lane_px": L, "lanes_out": None}
    sign = min(cand, key=lambda s_: cand[s_])
    dist = float(cand[sign])
    other = cand.get(-sign)
    d = dist / L * LANE
    spread = float(np.std([x for x, _ in ends[sign]])) / L * LANE
    sigma = 0.2 + spread + 0.03 * d
    if other is not None and other < dist + 2 * L:
        sigma += 0.8          # la serie termina cerca a ambos lados: no está claro cuál es el bordillo
    if other is None and d > 4.5:
        sigma += d            # solo se ve un borde y está lejos: probablemente el borde externo
    return {"d": d, "sigma_d": sigma, "lane_px": L, "lanes_out": None if other is None else float(other / L)}


@dataclass
class FrameGeometry:
    """Lo medido en un frame alrededor del grupo."""
    ppm_fit: tuple                  # ppm(y) = a + b·y (px/m en función de la fila del pie)
    phi: float                      # dirección de las líneas en la imagen (rad)
    u_fwd: np.ndarray               # vector unitario de imagen "hacia adelante" en la pista
    lane_px: float | None
    head_on: bool
    alpha: float
    k: float

    def ppm(self, y):
        a, b = self.ppm_fit
        return max(5.0, a + b * y)

    def J(self, y):
        """Columnas: px por metro hacia adelante (a_s) y transversal (a_d) a la fila y."""
        p = self.ppm(y)
        ca, sa = math.cos(self.alpha), math.sin(self.alpha)
        a_s = p * np.array([ca, self.k * sa])
        a_d = p * np.array([-sa, self.k * ca])
        if np.dot(a_s, self.u_fwd) < 0:
            a_s = -a_s
        return a_s, a_d


_AL = np.radians(np.arange(-89.5, 90, 1.0))
_K = np.exp(np.linspace(np.log(0.04), np.log(0.9), 40))
_AG, _KG = np.meshgrid(_AL, _K, indexing="ij")


def fit_view(phi, ppm, sigma=None, k_prior=0.25):
    """Ángulo α de la pista respecto al plano de la imagen y escorzo k = sen(elevación) de un mapa
    de perspectiva débil  a_s = ppm·(cos α, k sen α),  a_d = ppm·(−sen α, k cos α).

    Observaciones: la dirección de las líneas en la imagen (φ) y, si se ve, el espaciado entre
    calles medido perpendicular a ellas (σ px/m). Se ajusta por grilla con un prior suave sobre k
    (cámaras de TV elevadas 5–35°), en vez de despejar: con mediciones ruidosas la solución
    cerrada se sale de rango."""
    phi_p = np.arctan2(_KG * np.sin(_AG), np.cos(_AG))
    dphi = (phi_p - phi + np.pi / 2) % np.pi - np.pi / 2
    cost = (dphi / 0.06) ** 2 + ((np.log(_KG) - np.log(k_prior)) / 1.5) ** 2
    if sigma:
        sig_p = ppm * _KG / np.sqrt(np.cos(_AG) ** 2 + _KG ** 2 * np.sin(_AG) ** 2)
        cost = cost + ((np.log(sig_p) - np.log(sigma)) / 0.25) ** 2
    i = np.unravel_index(np.argmin(cost), cost.shape)
    return float(_AG[i]), float(_KG[i])


def fit_ppm(feet_y, heights):
    """Píxeles por metro según la fila del pie: en suelo plano crece lineal con la fila.
    Ajuste robusto (los cuerpos tapados o agachados dan cajas bajas)."""
    ppm = heights / BODY_H
    if len(ppm) < 3 or np.ptp(feet_y) < 20:
        return float(np.median(ppm)), 0.0
    A = np.stack([np.ones_like(feet_y), feet_y], 1)
    w = np.ones_like(ppm)
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(A * w[:, None], ppm * w, rcond=None)
        r = ppm - A @ coef
        s = 1.4826 * np.median(np.abs(r)) + 1e-6
        w = 1 / np.maximum(1, np.abs(r) / (2 * s))
    a, b = coef
    if b < 0:   # más abajo en la imagen = más cerca = más grande; si no, no hay perspectiva útil
        return float(np.median(ppm)), 0.0
    return float(a), float(b)


def measure_frame(frame, boxes, runners, fwd_hint: np.ndarray | None = None,
                  prev_geo: "FrameGeometry | None" = None, smooth: float = 0.25):
    """Geometría local y posición relativa de cada corredor dentro del frame.

    `prev_geo`: geometría del frame anterior del mismo plano (None tras un corte); si se da, la
    vista se suaviza hacia ella con peso `smooth` para lo nuevo.

    -> (FrameGeometry | None, [dict(idx, foot, ds, sigma_ds, d, sigma_d)]) con ds en metros
       relativo al centro del grupo (+ = adelante) y d en metros al bordillo (o None)."""
    if len(runners) == 0:
        return None, []
    H, W = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    b = boxes[runners]
    feet = np.stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]], 1)
    hts = b[:, 3] - b[:, 1]
    a_, b_ = fit_ppm(feet[:, 1], hts)
    ppm_of = lambda y: max(5.0, a_ + b_ * y)
    mask = line_mask(frame, boxes=b, ignore=IGNORE_TV)
    # de cerca una línea (5 cm) mide más que la ventana de line_mask y sale como dos bordes: cerrar
    kc = int(np.clip(0.12 * ppm_of(float(np.median(feet[:, 1]))), 1, 25)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc)))
    grass = grass_mask(hsv)
    red = tartan_mask(hsv)
    excl = [tuple(x) for x in b] + IGNORE_TV
    excl_mask = np.zeros((H, W), bool)
    for (x1, y1, x2, y2) in excl:
        excl_mask[max(0, int(y1)):int(y2), max(0, int(x1)):int(x2)] = True

    phis = [local_direction(mask, f, int(max(60, 2.5 * ppm_of(f[1]))), excl) for f in feet]
    valid = [(p, c) for p, c in phis if p is not None and c > 0.3]
    close_up = float(np.median(hts)) > 220          # primer plano: los cuerpos tapan casi todo el suelo
    phi_long = long_segments_direction(mask, top=int(feet[:, 1].min() - 0.3 * np.median(hts)))
    blind = False
    if close_up:
        # De cerca los cuerpos tapan las calles y junto a los pies dominan marcas transversales:
        # solo se confía en una dirección de pista clara y "de frente" (calles casi verticales).
        loose = [(p, c) for p, c in phis if p is not None and c > 0.15]
        steep = [(p, c) for p, c in loose if abs(p) > math.radians(50)]
        if len(steep) >= max(2, len(loose) // 2):
            valid = steep
        else:
            blind = True       # sin geometría confiable: identidad y etiquetas sí, medición no
            valid = valid or loose or ([(phi_long, 1.0)] if phi_long is not None else [(0.0, 1.0)])
    if not valid:
        if phi_long is None:
            return None, []
        valid = [(phi_long, 1.0)]
    P = np.array([p for p, _ in valid]); C = np.array([c for _, c in valid])
    phi_g = 0.5 * math.atan2(np.sum(C * np.sin(2 * P)), np.sum(C * np.cos(2 * P)))
    lat = [lateral_measure(mask, grass, excl_mask, f, (p if p is not None and c > 0.3 else phi_g), ppm_of(f[1]), red=red)
           for f, (p, c) in zip(feet, phis)]
    lanes = [l["lane_px"] for l in lat if l is not None]
    lane_px = float(np.median(lanes)) if lanes else None
    ppm_c = ppm_of(float(np.median(feet[:, 1])))

    alpha, k = fit_view(phi_g, ppm_c, lane_px / LANE if lane_px else None)
    if prev_geo is not None:
        # Dentro de un plano la vista cambia despacio: re-ajustarla de cero en cada frame hace que
        # la dirección salte >20° en ~10 % de los frames y reescala todos los Δs a la vez (saltos
        # de >1 m que el Kalman lee como velocidad). Se suaviza hacia el frame anterior.
        s = smooth
        axial = lambda p_old, p_new: 0.5 * math.atan2((1 - s) * math.sin(2 * p_old) + s * math.sin(2 * p_new),
                                                       (1 - s) * math.cos(2 * p_old) + s * math.cos(2 * p_new))
        phi_g = axial(prev_geo.phi, phi_g)
        alpha = axial(prev_geo.alpha, alpha)
        k = math.exp((1 - s) * math.log(prev_geo.k) + s * math.log(k))
        a_ = (1 - s) * prev_geo.ppm_fit[0] + s * a_
        b_ = (1 - s) * prev_geo.ppm_fit[1] + s * b_
    head_on = abs(math.cos(alpha)) < 0.35

    # hacia adelante: lo da el movimiento (fwd_hint); de frente, los corredores vienen hacia la cámara.
    # Dentro de un plano, "adelante" no se da vuelta: manda la continuidad con el frame anterior.
    u = np.array([math.cos(phi_g), math.sin(phi_g)])
    if prev_geo is not None:
        u = u if np.dot(u, prev_geo.u_fwd) >= 0 else -u
    elif head_on:
        u = u if u[1] > 0 else -u
    elif fwd_hint is not None and np.dot(u, fwd_hint) < 0:
        u = -u
    geo = FrameGeometry((a_, b_), phi_g, u, lane_px, head_on, alpha, k)

    c = np.median(feet, 0)
    # lateral relativo con el mapa local (para quien no tiene medición propia del bordillo)
    dd_rel = []
    for f in feet:
        a_s, a_d = geo.J((f[1] + c[1]) / 2)
        sol, *_ = np.linalg.lstsq(np.stack([a_s, a_d], 1), f - c, rcond=None)
        dd_rel.append(float(sol[1]))
    dd_rel = np.array(dd_rel)
    have = [j for j, l in enumerate(lat) if l and l.get("d") is not None and -0.5 < l["d"] < 11]
    if have:
        # ¿hacia dónde crece d en el mapa local? (signo de a_d): se alinea con las mediciones
        dm = np.array([lat[j]["d"] for j in have])
        sgn = 1.0
        if len(have) >= 2 and np.ptp(dd_rel[have]) > 0.3:
            sgn = 1.0 if np.corrcoef(dd_rel[have], dm)[0, 1] >= 0 else -1.0
        off = float(np.median(dm - sgn * dd_rel[have]))
        fill = lambda j: (off + sgn * dd_rel[j], 0.8 + 0.4 * abs(dd_rel[j]))
    else:
        fill = lambda j: (None, None)
    out = []
    for j, (f, l) in enumerate(zip(feet, lat)):
        d = l["d"] if l and l.get("d") is not None and -0.5 < l["d"] < 11 else None
        sd = l["sigma_d"] if d is not None else None
        if d is None:
            d, sd = fill(j)
        a_s, a_d = geo.J((f[1] + c[1]) / 2)
        sol, *_ = np.linalg.lstsq(np.stack([a_s, a_d], 1), f - c, rcond=None)
        ds = float(sol[0])
        # zancada: el pie se mueve ±~12 % del alto en la imagen; escala del cuerpo ±5 %;
        # y el escorzo k es incierto cuando lo longitudinal es profundidad (|cos α| chico)
        sds = (0.12 * hts[j] / max(1e-6, np.linalg.norm(a_s)) + 0.05 * abs(ds) + 0.15
               + 0.5 * abs(ds) * (1 - abs(math.cos(alpha))))
        if blind:
            ds, sds, d, sd = 0.0, 1e3, None, None
        out.append({"idx": int(runners[j]), "foot": f, "ds": float(ds), "sigma_ds": float(sds),
                    "d": d, "sigma_d": sd})
    return geo, out


# ------------------------------------------------------------------ apariencia (re-ID tras cortes)
def jersey_hist(frame, box):
    """Histograma de color de la camiseta (franja del torso, centro de la caja)."""
    x1, y1, x2, y2 = box
    h, w = y2 - y1, x2 - x1
    sub = frame[int(y1 + 0.18 * h):int(y1 + 0.5 * h), int(x1 + 0.25 * w):int(x2 - 0.25 * w)]
    if sub.size < 30:
        return None
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).ravel()
    return np.sqrt(hist / (hist.sum() + 1e-9)).astype(np.float32)


# ------------------------------------------------------------------ estado por atleta
@dataclass
class Athlete:
    id: int
    x: float              # metros recorridos desde la salida (sin envolver)
    u: float              # velocidad relativa al grupo (m/s)
    d: float              # metros al bordillo
    P: np.ndarray         # covarianza de (x, u)
    Pd: float             # varianza de d
    app: np.ndarray | None
    last_t: float
    seen: int = 1
    tid: int | None = None
    box: tuple | None = None
    d_seen: bool = False


class AthleteTracker:
    """Filtro de Kalman por atleta sobre (x, u) longitudinal y d lateral.

    predicción:  x += (v_grupo + u)·dt   (u se relaja a 0: nadie sostiene una velocidad relativa
                 para siempre)
    medición:    x = x_grupo + (Δs_atleta − Δs_del_que_va_adelante)   Δs medido dentro del frame
                 d = distancia al bordillo (cuando se ve el pasto)
    (x_grupo, v_grupo) vienen del filtro de zonas, que estima la cabeza de carrera; se ancla al
    atleta que va más adelante en el frame.
    Tras un corte las identidades del tracker de imagen cambian: se re-asignan por posición
    predicha + color de camiseta (asignación húngara).
    """

    def __init__(self, q_u=0.1, tau_u=15.0, gate_m=6.0, w_app=6.0, max_app=0.9, forget_s=40.0,
                 field_size: int | None = 12, beta: float = 0.03):
        # field_size: corredores en la serie (final del 1500 NCAA: 12). Nunca hay más atletas que
        # eso: si aparece "uno nuevo" con la serie completa, es alguien ya conocido tras un corte.
        # beta: cuánto corrige por frame el ancla común hacia el filtro de grupo dentro de un plano.
        self.field_size, self.beta = field_size, beta
        self.offset = None
        self.ath: dict[int, Athlete] = {}
        self.alias: dict[int, int] = {}        # id del tracker de imagen -> id de atleta
        self.next_id = 0
        self.q_u, self.tau_u, self.gate_m = q_u, tau_u, gate_m
        self.w_app, self.max_app, self.forget_s = w_app, max_app, forget_s
        self.t = None

    def predict(self, t, v_group):
        if self.t is None:
            self.t = t
            return
        dt = t - self.t
        if dt <= 0:
            return
        r = math.exp(-dt / self.tau_u)
        F = np.array([[1, dt], [0, r]])
        Q = np.array([[0.05 * dt, 0], [0, self.q_u ** 2 * dt]])
        for a in self.ath.values():
            a.x += (v_group + a.u) * dt
            a.u *= r
            a.P = F @ a.P @ F.T + Q
            a.Pd += 0.02 * dt
        self.t = t

    def update(self, t, x_group, meas, tids, boxes, frame, cut=False):
        """meas: salida de measure_frame; tids: id del tracker de imagen por medición (o None)."""
        if not meas:
            self._forget(t)
            return []
        lead = max(m["ds"] for m in meas)
        apps = [jersey_hist(frame, boxes[m["idx"]]) for m in meas]
        if cut:
            self.alias.clear()
            self.offset = None
        ids = [self.alias.get(int(tid)) if tid is not None else None for tid in tids]
        # Ancla común: x = Δs + offset. Dentro de un plano, offset se fija con los atletas ya
        # seguidos (sus predicciones), así que el que va adelante puede taparse sin mover a todos;
        # el filtro de grupo solo lo corrige despacio (beta). Tras un corte, viene del grupo.
        known = [(self.ath[i].x - meas[j]["ds"]) for j, i in enumerate(ids) if i is not None and i in self.ath]
        group_off = x_group - lead
        shift = 0.0
        if known and self.offset is not None:
            self.offset = float(np.median(known))
            # la corrección hacia el grupo traslada a todos por igual y NO entra en la velocidad
            # relativa u (si no, cada salto del filtro de grupo se leería como un sprint)
            shift = self.beta * (group_off - self.offset)
        else:
            self.offset = group_off
        z = [m["ds"] + self.offset for m in meas]
        seen_ids = set()
        for j, i in enumerate(ids):           # dos mediciones con el mismo atleta: el tracker se confundió
            if i is not None and i in seen_ids:
                ids[j] = None
            seen_ids.add(i)
        taken = {i for i in ids if i is not None}
        free = [a for a in self.ath.values() if a.id not in taken]
        new = [j for j, i in enumerate(ids) if i is None]
        if new and free:
            C = np.full((len(new), len(free)), 1e6)
            for r, j in enumerate(new):
                for c, a in enumerate(free):
                    gap = abs(z[j] - a.x)
                    da = 0.0 if apps[j] is None or a.app is None else float(np.linalg.norm(apps[j] - a.app))
                    if gap > self.gate_m + 3 * math.sqrt(a.P[0, 0]) or da > self.max_app:
                        continue
                    dz = gap / math.sqrt(a.P[0, 0] + meas[j]["sigma_ds"] ** 2 + 4.0)
                    dd = 0.0 if meas[j]["d"] is None else abs(meas[j]["d"] - a.d) / math.sqrt(a.Pd + 0.5)
                    C[r, c] = dz + 0.5 * dd + self.w_app * da
            rr, cc = linear_sum_assignment(C)
            for r, c in zip(rr, cc):
                if C[r, c] < 1e5:
                    ids[new[r]] = free[c].id
            # serie completa: los que siguen sin asignar son conocidos; se asignan sin compuertas
            n_known = len(self.ath)
            rest = [r for r in range(len(new)) if ids[new[r]] is None]
            used = {ids[j] for j in range(len(ids)) if ids[j] is not None}
            ghosts = [c for c, a in enumerate(free) if a.id not in used]
            if self.field_size and rest and ghosts and n_known >= self.field_size:
                C2 = np.zeros((len(rest), len(ghosts)))
                for ri, r in enumerate(rest):
                    j = new[r]
                    for gi, c in enumerate(ghosts):
                        a = free[c]
                        da = 1.0 if apps[j] is None or a.app is None else float(np.linalg.norm(apps[j] - a.app))
                        C2[ri, gi] = abs(z[j] - a.x) / 10 + self.w_app * da
                r2, c2 = linear_sum_assignment(C2)
                for ri, gi in zip(r2, c2):
                    ids[new[rest[ri]]] = free[ghosts[gi]].id
        out = []
        for j, m in enumerate(meas):
            if ids[j] is None:
                self.next_id += 1
                has_d = m["d"] is not None
                a = Athlete(self.next_id, z[j], 0.0, float(np.clip(m["d"], 0, 11)) if has_d else 1.0,
                            np.diag([m["sigma_ds"] ** 2 + 1.0, 0.5]), (m["sigma_d"] ** 2) if has_d else 4.0,
                            apps[j], t, d_seen=has_d)
                self.ath[a.id] = a
                ids[j] = a.id
            else:
                a = self.ath[ids[j]]
                R = m["sigma_ds"] ** 2
                innov = z[j] - a.x
                if R >= 1e5:                                # Δs sin sentido conocido: no informa
                    innov, R = 0.0, 1e6
                if innov ** 2 > 16 * (a.P[0, 0] + R):      # atípico: se usa, pero con poco peso
                    R *= (innov ** 2 / (16 * (a.P[0, 0] + R)))
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
                    a.Pd *= (1 - kd)
                    a.d_seen = True
                if apps[j] is not None:
                    a.app = apps[j] if a.app is None else 0.9 * a.app + 0.1 * apps[j]
                a.seen += 1
            a = self.ath[ids[j]]
            a.last_t, a.tid, a.box = t, tids[j], tuple(float(v) for v in boxes[m["idx"]])
            if tids[j] is not None:
                self.alias[int(tids[j])] = a.id
            out.append(a)
        if shift:
            for a in self.ath.values():
                a.x += shift
            self.offset += shift
        self._forget(t)
        return out

    def _forget(self, t):
        for k in [k for k, a in self.ath.items() if t - a.last_t > self.forget_s]:
            del self.ath[k]
        alive = set(self.ath)
        self.alias = {k: v for k, v in self.alias.items() if v in alive}
