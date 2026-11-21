"""Medición dentro de un frame: dónde está cada corredor respecto al grupo y al bordillo.

Lo relativo se mide dentro de un solo frame, así que paneos y zooms de la TV no importan.
Dos reglas en la imagen:

  - Lateral (d, metros al bordillo): las calles, 1,22 m. Desde los pies se cuentan calles hasta
    el bordillo, que es el final de la serie periódica de líneas (en Hayward no está pintado: es
    una baranda, y antes del pasto a veces hay 2-3 m de tartán). Las razones de distancia sobre
    una recta se conservan en perspectiva: no hace falta calibrar la cámara.
  - Longitudinal (Δs, quién va adelante y por cuánto): el cuerpo. La caja de un corredor mide
    ~1,75 m de alto (el ancho cambia ×3 con la zancada, no sirve de regla). La dirección de
    carrera en la imagen sale de las líneas de pista junto a cada corredor, y el escorzo, del
    espaciado entre calles: un mapa local de perspectiva débil (`fit_view`).

`ds` se devuelve en una orientación canónica de la imagen (`u_img`); el sentido "adelante" lo fija
la etapa con estado (pipeline.run) con el movimiento de los corredores respecto al fondo. De
frente (la recta se aleja de la cámara) adelante es hacia la cámara y ya viene fijado.

Todo trabaja internamente a 1280 px de ancho (los umbrales están en esa escala).
"""

import itertools
import math
from dataclasses import dataclass

import cv2
import numpy as np

from app.cv.zones.evidence import line_mask

BODY_H = 1.75  # m: alto de la caja de un corredor en carrera
LANE = 1.22  # m: ancho de calle
WORK_W = 1280
# gráficos de TV en 1280x720 (ticker, marcador, logo) [inferido] de la transmisión NCAA 2025
IGNORE_TV = [(0, 645, 1280, 720), (990, 555, 1225, 645), (45, 28, 240, 66)]
CLOSE_UP_PX = 220  # alto mediano de caja (a 1280 px) desde el que es un primer plano
JERSEY_BINS = (12, 4)
JERSEY_SIZE = JERSEY_BINS[0] * JERSEY_BINS[1]


def _hsv_masks(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, s, v = cv2.split(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))
    red = (((h < 14) | (h > 165)) & (s > 70) & (v > 60)).astype(np.uint8)
    grass = ((h > 33) & (h < 90) & (s > 50) & (v > 40)).astype(np.uint8)
    return red, grass


# ------------------------------------------------------------------ ¿quién es corredor?
def select_runners(boxes: np.ndarray, red: np.ndarray, ignore=IGNORE_TV) -> np.ndarray:
    """Índices de cajas que son corredores: pies sobre tartán, alto parecido al del grupo,
    fuera de los gráficos de TV. Descarta público, jueces en el pasto y camarógrafos."""
    if len(boxes) == 0:
        return np.zeros(0, int)
    height, width = red.shape
    ok = []
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        fx, fy = (x1 + x2) / 2, y2
        if any(a <= fx <= c and b <= fy <= d for a, b, c, d in ignore):
            continue
        r = max(3, int(0.08 * (y2 - y1)))
        xa, xb = int(max(0, fx - 2 * r)), int(min(width, fx + 2 * r + 1))
        patch = red[int(max(0, fy - r)) : int(min(height, fy + r + 1)), xa:xb]
        if patch.size and patch.mean() > 0.3:
            ok.append(i)
    keep = np.array(ok, int)
    if len(keep) >= 3:
        h = boxes[keep, 3] - boxes[keep, 1]
        med = np.median(h)
        keep = keep[(h > 0.35 * med) & (h < 2.2 * med)]
    return keep


# ------------------------------------------------------------------ dirección de las líneas
def local_direction(mask, foot, radius, exclude) -> tuple[float | None, float]:
    """Orientación (rad, en [-π/2, π/2)) de las líneas cerca de un punto: tensor de estructura
    de la máscara de líneas en una ventana, sin cajas ni gráficos. -> (phi | None, coherencia)"""
    height, width = mask.shape
    x0, y0 = int(max(0, foot[0] - radius)), int(max(0, foot[1] - radius))
    x1, y1 = int(min(width, foot[0] + radius)), int(min(height, foot[1] + radius))
    sub = mask[y0:y1, x0:x1].copy()
    for a, b, c, d in exclude:
        sub[
            max(0, int(b) - y0) : max(0, int(d) - y0), max(0, int(a) - x0) : max(0, int(c) - x0)
        ] = 0
    if sub.sum() < 40:
        return None, 0.0
    g = cv2.GaussianBlur(sub.astype(np.float32), (0, 0), 2.0)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    jxx, jyy, jxy = float((gx * gx).sum()), float((gy * gy).sum()), float((gx * gy).sum())
    theta = 0.5 * math.atan2(2 * jxy, jxx - jyy)  # dirección dominante del gradiente
    coherence = math.hypot(jxx - jyy, 2 * jxy) / (jxx + jyy + 1e-9)
    phi = (theta + math.pi) % math.pi - math.pi / 2  # las líneas son perpendiculares al gradiente
    return phi, coherence


def long_segments_direction(mask, top: int = 0, min_len: int = 90) -> float | None:
    """Orientación dominante de los segmentos largos de línea bajo la fila `top` (o None)."""
    sub = mask[max(0, top) : 645]
    segs = cv2.HoughLinesP(
        sub * 255, 1, np.pi / 180, threshold=50, minLineLength=min_len, maxLineGap=20
    )
    if segs is None:
        return None
    segs = segs.reshape(-1, 4).astype(float)
    dx, dy = segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]
    length, ang = np.hypot(dx, dy), np.arctan2(dy, dx)
    return 0.5 * math.atan2(np.sum(length * np.sin(2 * ang)), np.sum(length * np.cos(2 * ang)))


# ------------------------------------------------------------------ lateral
def _crossings(m: np.ndarray) -> list[float]:
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


def lateral_measure(mask, red, excl_mask, foot, phi, ppm, n_scans: int = 5) -> dict | None:
    """Distancia del pie al bordillo (m) contando calles en barridos transversales a las líneas.

    El espaciado entre cruces consecutivos da el ancho de calle en px (L). El bordillo es la
    última línea de la serie periódica del lado donde la serie termina antes (hacia afuera siguen
    las 8-9 calles). Si tras esa línea hay ~1 calle de tartán sin líneas y luego nada, esa línea
    era la 1|2 y el bordillo (sin pintar) está en el borde del tartán.
    -> dict(d | None, sigma_d, lane_px) o None si no hay líneas suficientes."""
    height, width = mask.shape
    u = np.array([math.cos(phi), math.sin(phi)])
    n = np.array([-u[1], u[0]])
    max_px = int(np.clip(10 * LANE * ppm, 80, 600))
    ts = np.arange(-max_px, max_px + 1)
    scans, gaps = [], []
    for k in range(n_scans):
        p = foot + (k - n_scans // 2) * 0.5 * ppm * u
        xs = np.round(p[0] + ts * n[0]).astype(int)
        ys = np.round(p[1] + ts * n[1]).astype(int)
        inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        m = np.zeros(len(ts), bool)
        e = np.ones(len(ts), bool)
        rd = np.zeros(len(ts), bool)
        m[inside] = mask[ys[inside], xs[inside]] > 0
        e[inside] = excl_mask[ys[inside], xs[inside]]
        rd[inside] = red[ys[inside], xs[inside]] > 0
        c = np.array(_crossings(m & ~e))
        for a_, b_ in itertools.pairwise(c):
            if not e[int(a_) : int(b_) + 1].any():
                gaps.append(b_ - a_)
        scans.append((c - max_px, e, rd | m))
    gaps_arr = np.sort(np.array(gaps))
    gaps_arr = gaps_arr[gaps_arr > max(3.0, 0.02 * ppm * LANE)]
    if len(gaps_arr) < 2:
        return None
    base = np.percentile(gaps_arr, 25)
    lane_px = float(np.median(gaps_arr[gaps_arr < 1.35 * base]))

    ends: dict[int, list[float]] = {+1: [], -1: []}
    for c, e, ground in scans:
        for sign in (+1, -1):
            # desde la línea más cercana, aunque quede hasta 1 calle del otro lado del pie
            # (corredor en la calle 1 con el bordillo sin pintar)
            cs = np.sort(c[c * sign > -1.05 * lane_px] * sign)
            if len(cs) == 0 or cs[0] > 1.3 * lane_px:
                continue
            last = cs[0]
            for x in cs[1:]:
                gap = x - last
                steps = round(gap / lane_px)
                if steps >= 1 and abs(gap - steps * lane_px) < 0.25 * lane_px * steps:
                    if steps > 1:  # hueco de 2+ calles solo si en medio hay una persona tapando
                        a_, b_ = sorted((int(last * sign + max_px), int(x * sign + max_px)))
                        if not e[a_:b_].any():
                            break
                    last = x
                elif gap < 0.5 * lane_px:
                    continue
                else:
                    break
            i_last = int(last * sign + max_px)
            beyond = int(i_last + sign * 1.6 * lane_px)
            if (
                not (0 <= beyond < len(ts))
                or e[min(beyond, i_last) : max(beyond, i_last)].mean() > 0.5
            ):
                continue
            run, j = 0, i_last + sign * 2
            while 0 <= j < len(ts) and (ground[j] or e[j]):  # una persona no corta el tartán
                run += 1
                j += sign
            ends[sign].append(last + run + 2 if 0.6 * lane_px < run < 1.4 * lane_px else last)
    cand = {s: float(np.median(v)) for s, v in ends.items() if len(v) >= max(2, n_scans // 2)}
    if not cand:
        return {"d": None, "sigma_d": None, "lane_px": lane_px}
    sign = min(cand, key=lambda s: cand[s])
    dist, other = cand[sign], cand.get(-sign)
    d = dist / lane_px * LANE
    sigma = 0.2 + float(np.std(ends[sign])) / lane_px * LANE + 0.03 * d
    if other is not None and other < dist + 2 * lane_px:
        sigma += 0.8  # la serie termina cerca a ambos lados: no está claro cuál es el bordillo
    if other is None and d > 4.5:
        sigma += d  # solo se ve un borde y está lejos: probablemente el borde externo
    return {"d": d, "sigma_d": sigma, "lane_px": lane_px}


# ------------------------------------------------------------------ mapa local suelo -> imagen
_AL = np.radians(np.arange(-89.5, 90, 1.0))
_K = np.exp(np.linspace(np.log(0.04), np.log(0.9), 40))
_AG, _KG = np.meshgrid(_AL, _K, indexing="ij")


def fit_view(phi: float, ppm: float, sigma: float | None = None, k_prior: float = 0.25):
    """α (ángulo de la pista respecto al plano de la imagen) y escorzo k = sen(elevación) de
    a_s = ppm·(cos α, k sen α), a_d = ppm·(−sen α, k cos α).

    Observa la dirección de las líneas (φ) y, si se ve, el espaciado entre calles medido
    perpendicular a ellas (σ px/m). Ajuste por grilla con prior suave sobre k (cámaras de TV
    elevadas 5-35°): con mediciones ruidosas la solución cerrada se sale de rango."""
    phi_p = np.arctan2(_KG * np.sin(_AG), np.cos(_AG))
    dphi = (phi_p - phi + np.pi / 2) % np.pi - np.pi / 2
    cost = (dphi / 0.06) ** 2 + ((np.log(_KG) - np.log(k_prior)) / 1.5) ** 2
    if sigma:
        sig_p = ppm * _KG / np.sqrt(np.cos(_AG) ** 2 + _KG**2 * np.sin(_AG) ** 2)
        cost = cost + ((np.log(sig_p) - np.log(sigma)) / 0.25) ** 2
    i = np.unravel_index(np.argmin(cost), cost.shape)
    return float(_AG[i]), float(_KG[i])


def fit_ppm(feet_y: np.ndarray, heights: np.ndarray) -> tuple[float, float]:
    """Píxeles por metro según la fila del pie: en suelo plano crece lineal con la fila.
    Ajuste robusto (los cuerpos tapados o agachados dan cajas bajas). -> (a, b): ppm = a + b·y"""
    ppm = heights / BODY_H
    if len(ppm) < 3 or np.ptp(feet_y) < 20:
        return float(np.median(ppm)), 0.0
    design = np.stack([np.ones_like(feet_y), feet_y], 1)
    w = np.ones_like(ppm)
    coef = np.array([np.median(ppm), 0.0])
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(design * w[:, None], ppm * w, rcond=None)
        r = ppm - design @ coef
        s = 1.4826 * np.median(np.abs(r)) + 1e-6
        w = 1 / np.maximum(1, np.abs(r) / (2 * s))
    a, b = coef
    if b < 0:  # más abajo = más cerca = más grande; si no, no hay perspectiva útil
        return float(np.median(ppm)), 0.0
    return float(a), float(b)


@dataclass
class FrameGeometry:
    ppm_fit: tuple[float, float]
    phi: float  # dirección de las líneas en la imagen (rad)
    u_img: np.ndarray  # dirección canónica de imagen sobre la que se mide ds
    lane_px: float | None
    head_on: bool
    blind: bool  # primer plano sin geometría confiable: no hay medición
    alpha: float
    k: float

    def ppm(self, y: float) -> float:
        a, b = self.ppm_fit
        return max(5.0, a + b * y)

    def jacobian(self, y: float) -> tuple[np.ndarray, np.ndarray]:
        """px por metro a lo largo (a_s, en el sentido de u_img) y a lo ancho (a_d)."""
        p = self.ppm(y)
        ca, sa = math.cos(self.alpha), math.sin(self.alpha)
        a_s = p * np.array([ca, self.k * sa])
        a_d = p * np.array([-sa, self.k * ca])
        if np.dot(a_s, self.u_img) < 0:
            a_s = -a_s
        return a_s, a_d


def _canonical(phi: float, head_on: bool) -> np.ndarray:
    u = np.array([math.cos(phi), math.sin(phi)])
    if head_on:  # de frente los corredores vienen hacia la cámara (abajo en la imagen)
        return u if u[1] > 0 else -u
    return u if (u[0] > 1e-9 or (abs(u[0]) <= 1e-9 and u[1] > 0)) else -u


# ------------------------------------------------------------------ medición del frame
def measure_frame(frame: np.ndarray, boxes: np.ndarray) -> tuple[FrameGeometry | None, list[dict]]:
    """Geometría local y posición relativa de cada corredor dentro del frame.

    boxes: [[x1, y1, x2, y2], ...] en píxeles del frame. -> (geometría | None, por corredor
    dict(idx, foot, ds, sigma_ds, d, sigma_d)) con ds en metros relativo al centro del grupo
    en el sentido de `u_img`, y d en metros al bordillo (o None)."""
    if len(boxes) == 0:
        return None, []
    scale = WORK_W / frame.shape[1]
    if abs(scale - 1) > 1e-3:
        frame = cv2.resize(
            frame, (WORK_W, round(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA
        )
    bx = np.asarray(boxes, float)[:, :4] * scale
    red, _ = _hsv_masks(frame)
    runners = select_runners(bx, red)
    if len(runners) == 0:
        return None, []
    b = bx[runners]
    feet = np.stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]], 1)
    hts = b[:, 3] - b[:, 1]
    a_, b_ = fit_ppm(feet[:, 1], hts)

    def ppm_of(y: float) -> float:
        return max(5.0, a_ + b_ * y)

    excl = [tuple(x) for x in b] + IGNORE_TV
    mask = line_mask(frame, ignore=[tuple(int(v) for v in x) for x in excl])
    # de cerca una línea (5 cm) es más ancha que la ventana de line_mask y sale como dos bordes
    kc = int(np.clip(0.12 * ppm_of(float(np.median(feet[:, 1]))), 1, 25)) | 1
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc))
    )
    excl_mask = np.zeros(mask.shape, bool)
    for x1, y1, x2, y2 in excl:
        excl_mask[max(0, int(y1)) : int(y2), max(0, int(x1)) : int(x2)] = True

    phis = [local_direction(mask, f, int(max(60, 2.5 * ppm_of(f[1]))), excl) for f in feet]
    valid = [(p, c) for p, c in phis if p is not None and c > 0.3]
    close_up = float(np.median(hts)) > CLOSE_UP_PX
    phi_long = long_segments_direction(mask, top=int(feet[:, 1].min() - 0.3 * np.median(hts)))
    blind = False
    if close_up:
        # de cerca los cuerpos tapan las calles y junto a los pies dominan marcas transversales:
        # solo se confía en una dirección clara "de frente" (calles casi verticales)
        loose = [(p, c) for p, c in phis if p is not None and c > 0.15]
        steep = [(p, c) for p, c in loose if abs(p) > math.radians(50)]
        if len(steep) >= max(2, len(loose) // 2):
            valid = steep
        else:
            blind = True
            valid = valid or loose or [(phi_long if phi_long is not None else 0.0, 1.0)]
    if not valid:
        if phi_long is None:
            return None, []
        valid = [(phi_long, 1.0)]
    P = np.array([p for p, _ in valid])
    C = np.array([c for _, c in valid])
    phi_g = 0.5 * math.atan2(np.sum(C * np.sin(2 * P)), np.sum(C * np.cos(2 * P)))
    lat = [
        lateral_measure(
            mask, red, excl_mask, f, p if p is not None and c > 0.3 else phi_g, ppm_of(f[1])
        )
        for f, (p, c) in zip(feet, phis, strict=True)
    ]
    lanes = [lm["lane_px"] for lm in lat if lm is not None]
    lane_px = float(np.median(lanes)) if lanes else None
    ppm_c = ppm_of(float(np.median(feet[:, 1])))
    alpha, k = fit_view(phi_g, ppm_c, lane_px / LANE if lane_px else None)
    head_on = abs(math.cos(alpha)) < 0.35
    geo = FrameGeometry(
        (a_, b_), phi_g, _canonical(phi_g, head_on), lane_px, head_on, blind, alpha, k
    )

    c = np.median(feet, 0)
    dd_rel = []
    for f in feet:
        a_s, a_d = geo.jacobian((f[1] + c[1]) / 2)
        sol, *_ = np.linalg.lstsq(np.stack([a_s, a_d], 1), f - c, rcond=None)
        dd_rel.append(float(sol[1]))
    dd_rel_arr = np.array(dd_rel)
    have = [j for j, lm in enumerate(lat) if lm and lm.get("d") is not None and -0.5 < lm["d"] < 11]
    sgn, off = 1.0, None
    if have:  # lateral relativo (mapa local) para quien no tiene medición propia del bordillo
        dm = np.array([lat[j]["d"] for j in have])
        if len(have) >= 2 and np.ptp(dd_rel_arr[have]) > 0.3:
            sgn = 1.0 if np.corrcoef(dd_rel_arr[have], dm)[0, 1] >= 0 else -1.0
        off = float(np.median(dm - sgn * dd_rel_arr[have]))

    out = []
    for j, (f, lm) in enumerate(zip(feet, lat, strict=True)):
        d = lm["d"] if lm and lm.get("d") is not None and -0.5 < lm["d"] < 11 else None
        sd = lm["sigma_d"] if d is not None else None
        if d is None and off is not None:
            d, sd = off + sgn * dd_rel_arr[j], 0.8 + 0.4 * abs(dd_rel_arr[j])
        a_s, a_d = geo.jacobian((f[1] + c[1]) / 2)
        sol, *_ = np.linalg.lstsq(np.stack([a_s, a_d], 1), f - c, rcond=None)
        ds = float(sol[0])
        # zancada (±~12 % del alto), escala del cuerpo (±5 %) y escorzo incierto de frente
        sds = (
            0.12 * hts[j] / max(1e-6, float(np.linalg.norm(a_s)))
            + 0.05 * abs(ds)
            + 0.15
            + 0.5 * abs(ds) * (1 - abs(math.cos(alpha)))
        )
        if blind:
            ds, sds, d, sd = 0.0, 1e3, None, None
        out.append(
            {
                "idx": int(runners[j]),
                "foot": (f / scale).tolist(),
                "ds": ds,
                "sigma_ds": float(sds),
                "d": None if d is None else float(d),
                "sigma_d": None if sd is None else float(sd),
            }
        )
    return geo, out


# ------------------------------------------------------------------ apariencia y movimiento
def jersey_hist(frame: np.ndarray, box) -> np.ndarray | None:
    """Histograma de color de la camiseta (franja del torso, centro de la caja); raíz cuadrada
    del histograma normalizado (distancia L2 = Hellinger)."""
    x1, y1, x2, y2 = box[:4]
    h, w = y2 - y1, x2 - x1
    sub = frame[int(y1 + 0.18 * h) : int(y1 + 0.5 * h), int(x1 + 0.25 * w) : int(x2 - 0.25 * w)]
    if sub.size < 30:
        return None
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, list(JERSEY_BINS), [0, 180, 0, 256]).ravel()
    return np.sqrt(hist / (hist.sum() + 1e-9)).astype(np.float32)


def motion_gray(frame: np.ndarray) -> np.ndarray:
    """Miniatura gris de la zona útil (sin gráficos de TV) para medir el movimiento del fondo."""
    h = frame.shape[0]
    roi = frame[int(60 / 720 * h) : int(640 / 720 * h)]
    return cv2.cvtColor(
        cv2.resize(roi, (320, 145), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY
    ).astype(np.float32)


def background_shift(prev_gray: np.ndarray, gray: np.ndarray, frame_shape) -> list[float]:
    """Desplazamiento del fondo (px del frame) entre dos miniaturas: correlación de fase.
    Con la cámara siguiendo al grupo, el fondo se mueve al revés que los corredores."""
    (sx, sy), _ = cv2.phaseCorrelate(prev_gray, gray)
    h, w = frame_shape[:2]
    return [float(sx * w / 320), float(sy * (580 / 720 * h) / 145)]
