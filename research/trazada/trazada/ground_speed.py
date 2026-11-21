"""Velocidad absoluta del grupo medida contra el suelo, en video de TV.

La cámara panea siguiendo al grupo, así que en la imagen los corredores casi no se mueven y el
suelo corre hacia atrás. Velocidad de un corredor respecto a la pista:

    Δ_imagen(corredor) − Δ_imagen(suelo)   ->  metros con el mapa local J(y) (athletes.FrameGeometry)

El problema es medir Δ_imagen(suelo): el tartán no tiene textura y las líneas de las calles son
paralelas a la carrera (no dicen cuánto se avanzó: problema de apertura). Sí sirven las marcas
**transversales**: rayas de zonas de relevo y salidas, números de calle, postes de la baranda del
bordillo. Se arma una imagen solo con bordes transversales a la dirección de carrera (gradiente
casi paralelo a ella), dentro del tartán y su borde, sin corredores ni gráficos de TV, y se mide
su desplazamiento entre dos frames con correlación de fase. Si no hay marcas transversales
suficientes o la correlación es débil, no se opina.

Con la cámara rotando sobre un punto fijo (lo normal en TV) el corrimiento del suelo en la imagen
es casi uniforme, así que no importa a qué profundidad estén las marcas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .athletes import tartan_mask


@dataclass
class GroundShift:
    dx: float
    dy: float
    response: float          # pico de la correlación de fase (0..1)
    marks: float             # fracción de píxeles con bordes transversales en la región


def lane_direction_field(lines, u, win=61):
    """Dirección local de las líneas de calle (vector unitario por píxel), con tensor de estructura
    sobre la máscara de líneas suavizado en `win` px. En las curvas las calles giran: una sola
    dirección global deja pasar las líneas como si fueran marcas transversales. Donde no hay
    líneas cerca se usa u."""
    m = lines.astype(np.float32)
    gx = cv2.Sobel(m, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(m, cv2.CV_32F, 0, 1, ksize=3)
    jxx = cv2.boxFilter(gx * gx, -1, (win, win))
    jyy = cv2.boxFilter(gy * gy, -1, (win, win))
    jxy = cv2.boxFilter(gx * gy, -1, (win, win))
    # orientación del gradiente dominante (perpendicular a las líneas) -> dirección de las líneas
    theta = 0.5 * np.arctan2(2 * jxy, jxx - jyy) + np.pi / 2
    strength = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2)
    has = strength > 0.05 * (strength.max() + 1e-6)
    dx = np.where(has, np.cos(theta), u[0]).astype(np.float32)
    dy = np.where(has, np.sin(theta), u[1]).astype(np.float32)
    return dx, dy


def transverse_edges(frame, u, region, lines=None, cos_max=math.cos(math.radians(25))):
    """Magnitud de gradiente solo donde el borde cruza la dirección local de carrera (gradiente ∥ a
    las calles). `lines`: máscara de líneas de calle para la dirección local; si no, u global."""
    g = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy) + 1e-6
    ux, uy = lane_direction_field(lines, u) if lines is not None else (u[0], u[1])
    along = np.abs(gx * ux + gy * uy) / mag
    keep = (along > cos_max) & (mag > 40) & region
    return np.where(keep, mag, 0).astype(np.float32), float(keep.mean())


def ground_region(frame, boxes, ignore, pad=0.15):
    """Tartán y su borde inmediato (líneas, bordillo), sin personas ni gráficos de TV.
    `boxes`: TODAS las personas detectadas (jueces y camarógrafos en el pasto también se mueven)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    reg = cv2.dilate(tartan_mask(hsv), np.ones((7, 7), np.uint8)).astype(bool)
    H, W = reg.shape
    for (x1, y1, x2, y2) in boxes:
        px, py = pad * (x2 - x1), pad * (y2 - y1)
        reg[max(0, int(y1 - py)):int(y2 + py), max(0, int(x1 - px)):int(x2 + px)] = False
    for (x1, y1, x2, y2) in ignore:
        reg[y1:y2, x1:x2] = False
    return reg


def shadow_free_region(frame, boxes, ignore, pad_x=0.5, below=0.35):
    """Como ground_region, pero sacando además una franja ancha alrededor de cada persona y
    debajo de sus pies (sombras y piernas fuera de la caja se mueven con el corredor)."""
    reg = ground_region(frame, [], ignore)
    for (x1, y1, x2, y2) in boxes:
        w, h = x2 - x1, y2 - y1
        reg[max(0, int(y1 - 0.1 * h)):int(y2 + below * h), max(0, int(x1 - pad_x * w)):int(x2 + pad_x * w)] = False
    return reg


def corner_shift(gray_prev, gray_now, region, max_pts=300, tol=2.0, min_inliers=8):
    """Desplazamiento del suelo con esquinas (fin de rayas, números, postes): sin problema de
    apertura. LK piramidal + consenso RANSAC de traslación. -> (dx, dy, n_inliers, n_pts)."""
    pts = cv2.goodFeaturesToTrack(gray_prev, max_pts, 0.02, 7, mask=region.astype(np.uint8))
    if pts is None or len(pts) < min_inliers:
        return None
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gray_now, pts, None, winSize=(21, 21), maxLevel=4)
    back, st2, _ = cv2.calcOpticalFlowPyrLK(gray_now, gray_prev, nxt, None, winSize=(21, 21), maxLevel=4)
    ok = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.linalg.norm(back - pts, axis=2)[:, 0] < 1.0)
    d = (nxt - pts)[ok, 0]
    if len(d) < min_inliers:
        return None
    best = None
    for c in d:                          # RANSAC exhaustivo: cada vector es una hipótesis
        inl = np.linalg.norm(d - c, axis=1) < tol
        if best is None or inl.sum() > best.sum():
            best = inl
    if best.sum() < min_inliers:
        return None
    m = d[best].mean(0)
    return float(m[0]), float(m[1]), int(best.sum()), int(len(d))


def ground_shift(feat_prev, feat_now) -> tuple[float, float, float]:
    """Desplazamiento (dx, dy) en píxeles del suelo de prev a now, y la fuerza del pico."""
    if feat_prev.shape != feat_now.shape:
        return 0.0, 0.0, 0.0
    win = cv2.createHanningWindow(feat_now.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(np.sqrt(feat_prev), np.sqrt(feat_now), win)
    return float(dx), float(dy), float(resp)


def speed_from_shift(geo, runner_delta, ground_delta, y_feet, dt):
    """(Δs m/s, Δd m/s) del grupo: movimiento de los corredores respecto al suelo, en metros."""
    rel = np.asarray(runner_delta, float) - np.asarray(ground_delta, float)
    a_s, a_d = geo.J(y_feet)
    sol, *_ = np.linalg.lstsq(np.stack([a_s, a_d], 1), rel, rcond=None)
    return float(sol[0]) / dt, float(sol[1]) / dt


class GroundSpeedGate:
    """Junta las ventanas de 0,2 s y entrega una medición por segundo, solo si es confiable.

    Filtro físico/geométrico (no usa la verdad): vista lateral (|cos α| ≥ cos_min), velocidad de
    carrera plausible (v_lo–v_hi) y al menos `min_n` ventanas válidas en el último `span` s. Las
    ventanas de un mismo plano comparten errores (escala del mapa local), así que la mediana va con
    un σ fijo, no σ/√n."""

    def __init__(self, cos_min=0.8, v_lo=4.0, v_hi=10.0, span=1.0, min_n=8, sigma=0.8):
        self.cos_min, self.v_lo, self.v_hi = cos_min, v_lo, v_hi
        self.span, self.min_n, self.sigma = span, min_n, sigma
        self.buf: list[tuple[float, float]] = []
        self.last_out = -1e9

    def add(self, t, v, cos_a):
        v = abs(v)
        if cos_a >= self.cos_min and self.v_lo < v < self.v_hi:
            self.buf.append((t, v))

    def measure(self, t):
        self.buf = [(s, v) for s, v in self.buf if t - s <= self.span]
        if t - self.last_out < self.span or len(self.buf) < self.min_n:
            return None
        self.last_out = t
        return float(np.median([v for _, v in self.buf])), self.sigma
