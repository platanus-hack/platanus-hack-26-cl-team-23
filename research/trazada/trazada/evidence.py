"""Evidencia visual de "en qué parte de la pista está la cámara".

1. CameraMemory: reconocer la cámara/encuadre como lo haría una persona que ya vio una vuelta.
   La TV repite las mismas cámaras en cada vuelta (de frente en la recta opuesta, colchoneta del
   alto en la curva 1, ...). Cuando el filtro está seguro de dónde está, guarda la apariencia del
   frame junto con esa posición; cuando vuelve a ver algo parecido, "recuerda" dónde era.
   No usa etiquetas: aprende en línea, solo del pasado.

2. line_curvature: las rectas de la pista se ven rectas en la imagen desde cualquier punto de
   vista (una homografía lleva rectas a rectas); las curvas se ven curvas, salvo que se vea un
   tramo tan corto que la flecha del arco no se distingue. Cada línea pintada se ajusta con una
   parábola y se mide flecha/cuerda; el peso de la evidencia depende de cuánta línea se ve.
"""
from __future__ import annotations

import cv2
import numpy as np

from .broadcast import line_mask
from .geometry import STANDARD, Track
from .zones import zone_edges

# zona útil del frame de TV (sin el marcador de arriba ni las franjas de abajo), en fracción del alto
ROI = (60 / 720, 520 / 720)


# ------------------------------------------------------------------ apariencia
def descriptor(frame: np.ndarray) -> np.ndarray:
    """Color por bandas horizontales (tribuna / pista / pasto) + orientación de bordes por banda.
    Raíz cuadrada de histogramas normalizados: la distancia L2 equivale a Hellinger."""
    h = frame.shape[0]
    im = cv2.resize(frame[int(ROI[0] * h):int(ROI[1] * h)], (320, 115), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag, ang = np.hypot(gx, gy), np.mod(np.arctan2(gy, gx), np.pi)
    out = []
    for band in np.array_split(np.arange(im.shape[0]), 3):
        sl = slice(band[0], band[-1] + 1)
        hc = cv2.calcHist([hsv[sl]], [0, 1], None, [16, 8], [0, 180, 0, 256]).ravel()
        out.append(np.sqrt(hc / hc.sum()))
        ho, _ = np.histogram(ang[sl], bins=12, range=(0, np.pi), weights=mag[sl])
        out.append(np.sqrt(ho / (ho.sum() + 1e-6)))
    return np.concatenate(out).astype(np.float32)


class CameraMemory:
    """Recuerdos (apariencia -> posición en la pista) y verosimilitud sobre s."""

    def __init__(self, track: Track = STANDARD, max_std: float = 12.0, k: int = 3,
                 sigma_min: float = 12.0, floor: float = 0.15, accept: float = 0.75, scale: float = 0.6,
                 min_age_s: float = 40.0, temper: float = 0.5):
        self.track = track
        self.max_std, self.k, self.sigma_min, self.floor = max_std, k, sigma_min, floor
        # Distancia (Hellinger del descriptor) para "reconocer" un encuadre, absoluta: un umbral
        # relativo a las distancias vistas se agranda cuando la memoria tiene una sola cámara y
        # termina reconociendo cualquier cosa. En la final, aprendiendo de la vuelta 1:
        # d < 0,75 acepta ~55 % de los frames y de ésos acierta ~95 %.
        self.accept, self.scale = accept, scale
        # Solo se recuerda lo visto hace más de `min_age_s` (la vuelta anterior). Si no, el
        # recuerdo más parecido es el frame de hace un instante del mismo plano, que tira la
        # posición hacia atrás y congela el foco.
        self.min_age_s = min_age_s
        # Frames seguidos del mismo plano no son evidencia independiente: se atenúa (lik^temper).
        self.temper = temper
        self.D: list[np.ndarray] = []
        self.S: list[float] = []
        self.SD: list[float] = []
        self.T: list[float] = []

    def add(self, desc: np.ndarray, s: float, s_std: float, t: float) -> bool:
        if s_std > self.max_std:
            return False
        self.D.append(desc); self.S.append(s % self.track.lap); self.SD.append(s_std); self.T.append(t)
        return True

    def match(self, desc: np.ndarray, t: float):
        """-> (s_k, sigma_k, peso_k) de los k recuerdos más parecidos, o None si no se reconoce."""
        old = np.flatnonzero(np.array(self.T) <= t - self.min_age_s) if self.T else np.array([], int)
        if len(old) < 5:
            return None
        d = np.full(len(self.D), np.inf)
        d[old] = np.sqrt(((np.stack([self.D[i] for i in old]) - desc) ** 2).sum(1))
        idx = np.argsort(d)[:self.k]
        if d[idx[0]] > self.accept:
            return None   # encuadre no reconocido: no opina
        idx = idx[d[idx] <= self.accept]
        w = np.exp(-0.5 * (d[idx] / self.scale) ** 2)
        s = np.array(self.S)[idx]
        sig = np.maximum(self.sigma_min, np.array(self.SD)[idx] + 8.0)
        return s, sig, w / w.sum()

    def likelihood(self, desc: np.ndarray, t: float):
        m = self.match(desc, t)
        if m is None:
            return None
        s_k, sig_k, w_k = m
        tr = self.track

        def lik(s):
            s = np.asarray(s, dtype=float)
            ds = (s[:, None] - s_k[None] + tr.lap / 2) % tr.lap - tr.lap / 2
            return (self.floor + np.sum(w_k * np.exp(-0.5 * (ds / sig_k) ** 2), 1)) ** self.temper
        return lik


# ------------------------------------------------------------------ curvatura
IGNORE_TV = [(0, 520, 1280, 720), (0, 0, 1280, 60)]   # franjas de gráficos en 1280x720


def line_curvature(frame: np.ndarray, min_px: int = 120) -> dict:
    """Mide cuán curvas se ven las líneas pintadas.

    Devuelve:
      bend   flecha/cuerda ponderada por largo (0 = rectas; ~0,05+ = curva clara)
      chord  largo total de líneas medidas (px en 1280x720): cuánto se puede confiar
      n      número de trazos usados
    """
    h, w = frame.shape[:2]
    sx = 1280 / w
    f = cv2.resize(frame, (1280, 720)) if (w, h) != (1280, 720) else frame
    m = line_mask(f, ignore=IGNORE_TV)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    bends, chords = [], []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_px:
            continue
        ys, xs = np.nonzero(lab == i)
        P = np.stack([xs, ys], 1).astype(np.float64)
        c = P.mean(0)
        U, S, Vt = np.linalg.svd(P - c, full_matrices=False)
        u, v = (P - c) @ Vt[0], (P - c) @ Vt[1]
        chord = u.max() - u.min()
        if chord < 80 or S[1] / max(S[0], 1e-6) > 0.25:     # corto o "gordo" (persona, letrero)
            continue
        a = np.polyfit(u, v, 2)[0]
        bends.append(abs(a) * (chord / 2) ** 2 / chord)     # flecha / cuerda
        chords.append(chord)
    if not chords:
        return {"bend": 0.0, "chord": 0.0, "n": 0}
    chords = np.array(chords)
    return {"bend": float(np.sum(np.array(bends) * chords) / chords.sum()),
            "chord": float(chords.sum() / sx), "n": len(chords)}


def curvature_likelihood(feat: dict, track: Track = STANDARD, bend_curve: float = 0.012,
                         width: float = 0.7, min_chord: float = 600.0, strength: float = 2.0):
    """P(observación | s): curva vs recta, con un peso que crece con cuánta línea se vio.
    Con poca línea visible (primer plano, curva vista de muy cerca) la evidencia es plana.

    En la final del 1500: flecha/cuerda mediana 0,015 en curvas y 0,004 en rectas, con mucho
    solape (AUC 0,76: los teleobjetivos aplanan las curvas). Por eso es evidencia débil:
    `strength` = razón máxima curva:recta."""
    if feat["n"] == 0:
        return None
    conf = min(1.0, feat["chord"] / min_chord)
    z = (np.log(feat["bend"] + 1e-4) - np.log(bend_curve)) / width
    p_curve = 1 / (1 + np.exp(-z))   # 0..1
    e = zone_edges(track)
    c1, b, c2 = (e[0], e[2]), (e[2], e[3]), (e[3], e[5])

    def lik(s):
        s = np.mod(np.asarray(s, dtype=float), track.lap)
        in_curve = ((s >= c1[0]) & (s < c1[1])) | ((s >= c2[0]) & (s < c2[1]))
        p = np.where(in_curve, p_curve, 1 - p_curve)
        # mezcla con lo uniforme según la confianza y una fuerza máxima acotada
        return (1 - conf) + conf * (1 + (strength - 1) * p) / strength
    return lik
