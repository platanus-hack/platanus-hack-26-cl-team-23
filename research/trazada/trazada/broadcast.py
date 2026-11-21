"""Calibración automática para cámaras que se mueven (paneo/zoom), como la TV.

Idea: la cámara está fija en un punto (trípode) y solo gira y hace zoom. Su posición se
estima una vez; en cada frame se re-estiman solo orientación y zoom (4 parámetros)
haciendo calzar las líneas de pista del modelo con las líneas blancas de la imagen
(chamfer). Sin deriva: cada frame se ancla de nuevo contra la pista real.

Parámetros de cámara p = [x, y, z, yaw, pitch, roll, log_f]  (metros, radianes)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import least_squares

from .calibration import Calibration
from .geometry import Track

CLIP_PX = 12.0


# ------------------------------------------------------------------ líneas en la imagen
def line_mask(frame: np.ndarray, boxes=None, ignore=()) -> np.ndarray:
    """Píxeles de líneas blancas pintadas sobre el tartán rojo."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    red = (((h < 14) | (h > 165)) & (s > 70) & (v > 60)).astype(np.uint8)
    white = ((s < 70) & (v > 165)).astype(np.uint8)
    # una línea es angosta y tiene rojo a ambos lados: blanco con rojo cerca en dos direcciones opuestas
    k = 6
    near = lambda dx, dy: np.roll(cv2.dilate(red, np.ones((3, 3), np.uint8)), (dy, dx), axis=(0, 1))
    both_v = near(0, k) & near(0, -k)
    both_h = near(k, 0) & near(-k, 0)
    m = (white & (both_v | both_h)).astype(np.uint8)
    for (x1, y1, x2, y2) in (boxes if boxes is not None else []):
        m[max(0, int(y1)):int(y2) + 1, max(0, int(x1)):int(x2) + 1] = 0
    for (x1, y1, x2, y2) in ignore:
        m[y1:y2, x1:x2] = 0
    return m


def dist_field(mask: np.ndarray) -> np.ndarray:
    return cv2.distanceTransform((mask == 0).astype(np.uint8), cv2.DIST_L2, 3)


# ------------------------------------------------------------------ cámara
def rotation(yaw, pitch, roll):
    F = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    r0 = np.cross(F, [0, 0, 1.0]); r0 /= np.linalg.norm(r0)
    d0 = np.cross(F, r0)
    c, s = math.cos(roll), math.sin(roll)
    right, down = c * r0 + s * d0, -s * r0 + c * d0
    return np.stack([right, down, F])


def project(p, XYZ, size):
    w, h = size
    C = np.asarray(p[:3]); R = rotation(*p[3:6]); f = math.exp(p[6])
    Xc = (XYZ - C) @ R.T
    z = Xc[:, 2]
    ok = z > 0.5
    u = np.where(ok, f * Xc[:, 0] / np.maximum(z, 1e-6) + w / 2, -1e9)
    v = np.where(ok, f * Xc[:, 1] / np.maximum(z, 1e-6) + h / 2, -1e9)
    return np.stack([u, v], 1), ok


def homography(p, size) -> np.ndarray:
    """Plano del suelo (x, y, z=0) -> imagen."""
    w, h = size
    C = np.asarray(p[:3]); R = rotation(*p[3:6]); f = math.exp(p[6])
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]])
    P = K @ np.c_[R, -R @ C]
    G = P[:, [0, 1, 3]]
    return G / G[2, 2]


def to_calibration(p, size) -> Calibration:
    G = homography(p, size)
    H = np.linalg.inv(G)
    return Calibration(H / H[2, 2], tuple(size))


@dataclass
class TrackModel:
    track: Track
    s_range: tuple[float, float]
    step: float = 0.5

    def points(self):
        s = np.arange(self.s_range[0], self.s_range[1], self.step)
        pts = []
        for k in range(self.track.lanes + 1):
            x, y = self.track.track_to_world(s, np.full_like(s, k * self.track.lane_width))
            pts.append(np.c_[x, y, np.zeros_like(x)])
        return np.vstack(pts)


# ------------------------------------------------------------------ ajuste
def _residuals(p, XYZ, D, size, min_frac=0.25):
    w, h = size
    uv, ok = project(p, XYZ, size)
    inside = ok & (uv[:, 0] >= 0) & (uv[:, 0] < w - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < h - 1)
    r = np.full(len(XYZ), CLIP_PX * 0.6)          # puntos fuera de cuadro: costo neutro
    ui, vi = uv[inside, 0].astype(int), uv[inside, 1].astype(int)
    r[inside] = np.minimum(D[vi, ui], CLIP_PX)
    frac = inside.mean()
    if frac < min_frac:                           # no dejar que "mire a otro lado" para bajar el costo
        r = r + (min_frac - frac) * 4 * CLIP_PX
    return r


def coverage_cost(p, XYZ, mask_small, scale, size):
    """Chamfer inverso: qué tan lejos quedan las líneas detectadas del modelo proyectado."""
    w, h = mask_small.shape[1], mask_small.shape[0]
    uv, ok = project(p, XYZ, size)
    uv = uv[ok] * scale
    good = (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    canvas = np.zeros_like(mask_small)
    canvas[uv[good, 1].astype(int), uv[good, 0].astype(int)] = 1
    canvas = cv2.dilate(canvas, np.ones((2, 2), np.uint8))
    Dm = dist_field(canvas)
    ys, xs = np.nonzero(mask_small)
    if len(xs) == 0:
        return 1e9
    return float(np.mean(np.minimum(Dm[ys, xs], CLIP_PX * scale)))


def fit_initial(frame, model: TrackModel, bounds, boxes=None, ignore=(), n=6000, seed=0, verbose=True):
    """Búsqueda aleatoria gruesa a baja resolución + refinamiento. bounds: lista de (lo, hi) por parámetro."""
    h, w = frame.shape[:2]
    size = (w, h)
    m = line_mask(frame, boxes, ignore)
    D = dist_field(m)
    scale = 0.25
    m_small = cv2.resize(m, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    m_small = (m_small > 0).astype(np.uint8)
    D_small = dist_field(m_small)
    XYZ = TrackModel(model.track, model.s_range, step=2.0).points()
    rng = np.random.default_rng(seed)
    lo, hi = np.array(bounds).T
    cands = []
    for _ in range(n):
        p = lo + rng.random(len(lo)) * (hi - lo)
        uv, ok = project(p, XYZ, size)
        uvs = uv * scale
        inside = ok & (uvs[:, 0] >= 0) & (uvs[:, 0] < w * scale - 1) & (uvs[:, 1] >= 0) & (uvs[:, 1] < h * scale - 1)
        if inside.mean() < 0.15:
            continue
        c1 = np.mean(np.minimum(D_small[uvs[inside, 1].astype(int), uvs[inside, 0].astype(int)], CLIP_PX * scale))
        cands.append((c1, p))
    cands.sort(key=lambda c: c[0])
    best = None
    XYZf = model.points()
    for c1, p in cands[:40]:
        cov = coverage_cost(p, XYZ, m_small, scale, size)
        sol = least_squares(_residuals, p, args=(XYZf, D, size), loss="soft_l1", f_scale=3.0,
                            bounds=(lo - 1e-6, hi + 1e-6), max_nfev=200)
        cost = float(np.mean(_residuals(sol.x, XYZf, D, size))) + 0.5 * coverage_cost(sol.x, XYZ, m_small, scale, size)
        if best is None or cost < best[0]:
            best = (cost, sol.x)
    if verbose:
        print(f"[cam] mejor costo {best[0]:.2f} px  p={np.round(best[1], 3)}")
    return best[1], best[0]


class CameraTracker:
    """Re-estima orientación y zoom en cada frame con la posición de la cámara fija."""

    def __init__(self, p0, model: TrackModel, ignore=()):
        self.p = np.asarray(p0, float)
        self.XYZ = model.points()
        self.ignore = ignore
        self.cost = float("nan")

    def update(self, frame, boxes=None):
        h, w = frame.shape[:2]
        D = dist_field(line_mask(frame, boxes, self.ignore))
        C = self.p[:3]

        def res(q):
            return _residuals(np.r_[C, q], self.XYZ, D, (w, h))

        sol = least_squares(res, self.p[3:], loss="soft_l1", f_scale=3.0, max_nfev=60,
                            x_scale=[0.01, 0.01, 0.01, 0.05])
        self.p = np.r_[C, sol.x]
        self.cost = float(np.mean(res(sol.x)))
        return to_calibration(self.p, (w, h))


# ------------------------------------------------------------------ búsqueda vectorizada
def _batch_project(P, XYZ, size):
    """P: (B, 7) candidatos -> uv (B, N, 2), ok (B, N)."""
    w, h = size
    C, yaw, pitch, roll, f = P[:, :3], P[:, 3], P[:, 4], P[:, 5], np.exp(P[:, 6])
    F = np.stack([np.cos(pitch) * np.cos(yaw), np.cos(pitch) * np.sin(yaw), np.sin(pitch)], 1)
    r0 = np.stack([np.sin(yaw), -np.cos(yaw), np.zeros_like(yaw)], 1)     # F x up, normalizado
    d0 = np.cross(F, r0)
    cr, sr = np.cos(roll)[:, None], np.sin(roll)[:, None]
    right, down = cr * r0 + sr * d0, -sr * r0 + cr * d0
    rel = XYZ[None, :, :] - C[:, None, :]
    xc = np.einsum("bnk,bk->bn", rel, right)
    yc = np.einsum("bnk,bk->bn", rel, down)
    zc = np.einsum("bnk,bk->bn", rel, F)
    ok = zc > 0.5
    zc = np.maximum(zc, 1e-6)
    return np.stack([f[:, None] * xc / zc + w / 2, f[:, None] * yc / zc + h / 2], -1), ok


def search_targeted(frame, model: TrackModel, cam_box, target_sd_box, f_range, boxes=None, ignore=(),
                    n=200_000, batch=2000, seed=0, keep=30, verbose=True):
    """Muestrea cámara = posición + punto de la pista al que mira el centro de la imagen (mejor condicionado
    que muestrear ángulos), puntúa a 1/4 de resolución y refina los mejores a resolución completa."""
    h, w = frame.shape[:2]
    size = (w, h)
    m = line_mask(frame, boxes, ignore)
    D = dist_field(m)
    sc = 0.25
    ms = (cv2.resize(m, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) > 0).astype(np.uint8)
    Ds = dist_field(ms)
    XYZ = TrackModel(model.track, model.s_range, step=2.0).points()
    rng = np.random.default_rng(seed)
    (xl, xh), (yl, yh), (zl, zh) = cam_box
    (sl, sh), (dl, dh) = target_sd_box
    best = []
    for _ in range(n // batch):
        C = np.c_[rng.uniform(xl, xh, batch), rng.uniform(yl, yh, batch), rng.uniform(zl, zh, batch)]
        tx, ty = model.track.track_to_world(rng.uniform(sl, sh, batch), rng.uniform(dl, dh, batch))
        v = np.c_[tx, ty, np.zeros(batch)] - C
        yaw = np.arctan2(v[:, 1], v[:, 0])
        pitch = np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1]))
        roll = rng.uniform(-0.08, 0.08, batch)
        lf = rng.uniform(math.log(f_range[0]), math.log(f_range[1]), batch)
        P = np.c_[C, yaw, pitch, roll, lf]
        uv, ok = _batch_project(P, XYZ, size)
        uv = uv * sc
        ins = ok & (uv[..., 0] >= 0) & (uv[..., 0] < w * sc - 1) & (uv[..., 1] >= 0) & (uv[..., 1] < h * sc - 1)
        ui = np.clip(uv[..., 0], 0, w * sc - 1).astype(int)
        vi = np.clip(uv[..., 1], 0, h * sc - 1).astype(int)
        dist = np.minimum(Ds[vi, ui], CLIP_PX * sc)
        frac = ins.mean(1)
        cost = np.where(ins, dist, CLIP_PX * sc * 0.6).mean(1) + np.maximum(0, 0.3 - frac) * 10
        idx = np.argsort(cost)[:keep]
        best += [(cost[i], P[i]) for i in idx]
        best = sorted(best, key=lambda c: c[0])[:keep]
    XYZf = model.points()
    out = None
    for c0, p in best:
        cov = coverage_cost(p, XYZ, ms, sc, size)
        sol = least_squares(_residuals, p, args=(XYZf, D, size), loss="soft_l1", f_scale=3.0, max_nfev=300)
        cost = float(np.mean(_residuals(sol.x, XYZf, D, size))) + coverage_cost(sol.x, XYZ, ms, sc, size) / sc * 0.5
        if out is None or cost < out[0]:
            out = (cost, sol.x)
    if verbose:
        print(f"[cam] costo {out[0]:.2f}  p={np.round(out[1], 3)}")
    return out[1], out[0]


# ------------------------------------------------------------------ ajuste con líneas etiquetadas
def labeled_pixels(labels_img, groups: dict, step=3):
    """groups: {k (índice de línea, 0 = interior): [ids de componentes]} -> {k: (M, 2) píxeles}."""
    out = {}
    for k, ids in groups.items():
        ys, xs = np.nonzero(np.isin(labels_img, ids))
        out[k] = np.c_[xs, ys][::step].astype(float)
    return out


def _line_points(track: Track, s_range, k, step):
    s = np.arange(s_range[0], s_range[1], step)
    x, y = track.track_to_world(s, np.full_like(s, k * track.lane_width))
    return np.c_[x, y, np.zeros_like(x)]


def search_labeled(pix: dict, track: Track, s_range, size, cam_box, target_sd_box, f_range,
                   n=200_000, batch=400, seed=0, keep=20, verbose=True):
    rng = np.random.default_rng(seed)
    lines = {k: _line_points(track, s_range, k, 1.0) for k in pix}
    sub = {k: v[np.linspace(0, len(v) - 1, min(40, len(v))).astype(int)] for k, v in pix.items()}
    (xl, xh), (yl, yh), (zl, zh) = cam_box
    (sl, sh), (dl, dh) = target_sd_box
    best = []
    for _ in range(n // batch):
        C = np.c_[rng.uniform(xl, xh, batch), rng.uniform(yl, yh, batch), rng.uniform(zl, zh, batch)]
        tx, ty = track.track_to_world(rng.uniform(sl, sh, batch), rng.uniform(dl, dh, batch))
        v = np.c_[tx, ty, np.zeros(batch)] - C
        P = np.c_[C, np.arctan2(v[:, 1], v[:, 0]), np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1])),
                  rng.uniform(-0.08, 0.08, batch), rng.uniform(math.log(f_range[0]), math.log(f_range[1]), batch)]
        cost = np.zeros(batch)
        for k, Q in sub.items():
            uv, ok = _batch_project(P, lines[k], size)
            uv = np.where(ok[..., None], uv, 1e6)
            d = np.linalg.norm(uv[:, None, :, :] - Q[None, :, None, :], axis=-1).min(-1)  # (B, M)
            cost += np.minimum(d, 80).mean(1)
        idx = np.argsort(cost)[:keep]
        best = sorted(best + [(cost[i], P[i]) for i in idx], key=lambda c: c[0])[:keep]
    out = None
    for c0, p in best:
        x, c = refine_labeled(p, pix, track, s_range, size)
        if out is None or c < out[1]:
            out = (x, c)
    if verbose:
        print(f"[cam] error medio {out[1]:.2f} px  p={np.round(out[0], 3)}")
    return out


def refine_labeled(p, pix, track, s_range, size, fixed_pos=False):
    from scipy.spatial import cKDTree
    lines = {k: _line_points(track, s_range, k, 0.25) for k in pix}

    def res(q):
        pp = np.r_[p[:3], q] if fixed_pos else q
        r = []
        for k, Q in pix.items():
            uv, ok = project(pp, lines[k], size)
            if ok.sum() < 2:
                r.append(np.full(len(Q), 100.0)); continue
            d, _ = cKDTree(uv[ok]).query(Q)
            r.append(np.minimum(d, 100.0))
        return np.concatenate(r)

    q0 = p[3:] if fixed_pos else p
    sol = least_squares(res, q0, loss="soft_l1", f_scale=2.0, max_nfev=400)
    x = np.r_[p[:3], sol.x] if fixed_pos else sol.x
    return x, float(np.mean(res(sol.x)))


# ------------------------------------------------------------------ homografía libre por líneas
def grass_pixels(frame, ignore=(), boxes=(), n=600):
    """Pasto del interior: verde, sin personas ni gráficos. Debe quedar dentro del bordillo (d < 0)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    g = ((hsv[..., 0] > 35) & (hsv[..., 0] < 85) & (hsv[..., 1] > 60) & (hsv[..., 2] > 50)).astype(np.uint8)
    red = (((hsv[..., 0] < 14) | (hsv[..., 0] > 165)) & (hsv[..., 1] > 70)).astype(np.uint8)
    g = cv2.erode(g, np.ones((9, 9), np.uint8))
    # solo pasto cerca de la pista: evita confundir con butacas verdes de la tribuna
    g &= cv2.dilate(red, np.ones((121, 121), np.uint8))
    for (x1, y1, x2, y2) in list(ignore) + [tuple(map(int, b)) for b in boxes]:
        g[max(0, y1):y2, max(0, x1):x2] = 0
    ys, xs = np.nonzero(g)
    if len(xs) > n:
        sel = np.random.default_rng(1).choice(len(xs), n, replace=False)
        xs, ys = xs[sel], ys[sel]
    return np.c_[xs, ys].astype(float)


def refine_homography_lines(H0, pix: dict, track: Track, s_ref: float | None = None, reg: float = 0.02,
                            grass=None, w_grass: float = 0.5, prior_grid=None, w_prior: float = 0.0):
    """Ajusta H (imagen -> mundo, 8 GL) para que cada píxel de la línea k quede a d = k·ancho.

    El residuo está en metros sobre la pista. El único grado de libertad que las líneas no fijan
    (deslizar a lo largo de la pista) se ancla suavemente a H0 con `reg`.
    """
    H0 = H0 / H0[2, 2]
    P = np.vstack(list(pix.values()))
    K = np.concatenate([np.full(len(v), k) for k, v in pix.items()]) * track.lane_width
    Ph = np.c_[P, np.ones(len(P))]
    w0 = Ph @ H0.T
    s0, _ = track.world_to_track(w0[:, 0] / w0[:, 2], w0[:, 1] / w0[:, 2])

    def apply(h):
        H = np.r_[h, 1.0].reshape(3, 3)
        w = Ph @ H.T
        return track.world_to_track(w[:, 0] / w[:, 2], w[:, 1] / w[:, 2])

    Gh = np.c_[grass, np.ones(len(grass))] if grass is not None and len(grass) else None
    if prior_grid is not None and w_prior > 0:
        Qh = np.c_[prior_grid, np.ones(len(prior_grid))]
        q0 = Qh @ H0.T
        q0 = q0[:, :2] / q0[:, 2:]
    else:
        Qh = None

    def res(h):
        s, d = apply(h)
        ds = np.array([track.ds_wrap(a, b) for a, b in zip(s0[::25], s[::25])])
        r = [d - K, reg * ds]
        if Gh is not None:
            H = np.r_[h, 1.0].reshape(3, 3)
            w = Gh @ H.T
            _, dg = track.world_to_track(w[:, 0] / w[:, 2], w[:, 1] / w[:, 2])
            r.append(w_grass * np.maximum(0.0, dg + 0.15))
        if Qh is not None:   # no alejarse de la predicción (evita soluciones degeneradas)
            H = np.r_[h, 1.0].reshape(3, 3)
            q = Qh @ H.T
            r.append(w_prior * (q[:, :2] / q[:, 2:] - q0).ravel())
        return np.concatenate(r)

    sol = least_squares(res, H0.ravel()[:8], loss="soft_l1", f_scale=0.1, x_scale="jac", max_nfev=2000)
    H = np.r_[sol.x, 1.0].reshape(3, 3)
    _, d = apply(sol.x)
    return H, float(np.median(np.abs(d - K))), float(np.sum(np.minimum(res(sol.x) ** 2, 0.09)))


class HomographyTracker:
    """Sigue la calibración de una cámara que panea/hace zoom.

    1) predice con el movimiento del fondo (flujo óptico KLT, sin personas ni gráficos de TV)
    2) corrige contra las líneas de pista: cada píxel blanco se asigna a la línea k más cercana
       según la predicción y se reajusta H para que quede a d = k·ancho (ICP en metros).
    """

    def __init__(self, H0, track: Track, ignore=(), max_lines=None, correct=True, ecc_scale=0.5):
        self.H = H0 / H0[2, 2]
        self.correct, self.ecc_scale = correct, ecc_scale
        self.prev_lines = None
        self.track, self.ignore = track, ignore
        self.max_k = max_lines if max_lines is not None else track.lanes
        self.prev_gray = None
        self.err = float("nan")
        self.n_px = 0

    def predict(self, frame, boxes=()):
        """Movimiento de cámara frame anterior -> actual (homografía en píxeles), alineando con ECC
        las imágenes de líneas pintadas: el tartán casi no tiene textura, las líneas sí."""
        sc = self.ecc_scale
        cur = cv2.GaussianBlur(line_mask(frame, boxes, self.ignore).astype(np.float32), (0, 0), 3)
        cur = cv2.resize(cur, None, fx=sc, fy=sc)
        prev, self.prev_lines = self.prev_lines, cur
        if prev is None:
            return None
        W = np.eye(3, dtype=np.float32)
        try:
            _, W = cv2.findTransformECC(prev, cur, W, cv2.MOTION_HOMOGRAPHY,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5), None, 5)
        except cv2.error:
            return None
        S = np.diag([sc, sc, 1.0])
        return np.linalg.inv(S) @ W @ S

    def _mask_static(self, frame, boxes):
        # solo el SUELO (tartán, líneas, pasto): si la cámara se traslada (riel/dolly), lo que está
        # fuera del plano del suelo -baranda, carteles, tribuna- no sigue la misma homografía
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        red = ((hh < 14) | (hh > 165)) & (ss > 70) & (vv > 60)
        green = (hh > 35) & (hh < 85) & (ss > 60) & (vv > 50)
        m = cv2.erode((red | green).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))  # recupera las líneas blancas
        for (x1, y1, x2, y2) in boxes:
            m[max(0, int(y1) - 5):int(y2) + 5, max(0, int(x1) - 5):int(x2) + 5] = 0
        for (x1, y1, x2, y2) in self.ignore:
            m[y1:y2, x1:x2] = 0
        return m

    def update(self, frame, boxes=()):
        h, w = frame.shape[:2]
        G = self.predict(frame, boxes)
        if G is not None:
            self.H = self.H @ np.linalg.inv(G)
            self.H /= self.H[2, 2]
        if not self.correct:
            return Calibration(self.H.copy(), (w, h))

        # corrección con líneas: se asigna cada píxel blanco a la línea k más cercana y se reajusta.
        # Se prueban también las asignaciones corridas en ±1 pista; el pasto (que debe quedar dentro
        # del bordillo) desempata y evita que el ajuste "enganche" la línea vecina.
        m = line_mask(frame, boxes, self.ignore)
        ys, xs = np.nonzero(m)
        if len(xs) > 2500:
            sel = np.random.default_rng(0).choice(len(xs), 2500, replace=False)
            xs, ys = xs[sel], ys[sel]
        P = np.c_[xs, ys].astype(float)
        grass = grass_pixels(frame, self.ignore, boxes)
        gx, gy = np.meshgrid(np.linspace(100, w - 100, 6), np.linspace(80, h - 120, 5))
        grid = np.c_[gx.ravel(), gy.ravel()]
        H_pred = self.H.copy()
        best = None
        for shift in (0, -1, 1):
            Hs = self.H
            for it in range(2):
                if len(P) < 50:
                    break
                wpt = cv2.perspectiveTransform(P.reshape(-1, 1, 2), Hs).reshape(-1, 2)
                _, d = self.track.world_to_track(wpt[:, 0], wpt[:, 1])
                k = np.round(d / self.track.lane_width)
                ok = np.abs(d - k * self.track.lane_width) < 0.3
                k = k + (shift if it == 0 else 0)
                ok &= (k >= 0) & (k <= self.max_k)
                pix = {int(kk): P[ok & (k == kk)] for kk in np.unique(k[ok])}
                pix = {kk: v for kk, v in pix.items() if len(v) >= 10}
                if len(pix) < 2:
                    break
                Hs, med, cost = refine_homography_lines(Hs, pix, self.track, reg=0.05, grass=grass,
                                                        prior_grid=grid, w_prior=0.3)
                Hs = Hs / Hs[2, 2]
            else:
                if best is None or cost < best[0]:
                    best = (cost, Hs, med, int(ok.sum()), shift)
            if shift == 0 and best is not None and best[2] < 0.03:
                break  # ajuste limpio sin corrimiento: no hace falta probar los vecinos
        self.rejected = False
        if best is not None:
            # si la corrección mueve la grilla más de 2 m respecto a la predicción, no se le cree
            a = cv2.perspectiveTransform(grid.reshape(-1, 1, 2), H_pred).reshape(-1, 2)
            b = cv2.perspectiveTransform(grid.reshape(-1, 1, 2), best[1]).reshape(-1, 2)
            if np.median(np.linalg.norm(a - b, axis=1)) < 2.0:
                _, self.H, self.err, self.n_px, self.shift = best
            else:
                self.rejected = True
        return Calibration(self.H.copy(), (w, h))
