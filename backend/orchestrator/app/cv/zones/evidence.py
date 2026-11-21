"""Evidencia visual de "en qué parte de la pista está la cámara".

- Cortes de plano: histograma de color de la zona útil (sin gráficos de TV); un corte cambia todo
  el contenido, un paneo mantiene los colores de la escena.
- Memoria de cámaras: la TV repite las mismas cámaras cada vuelta; el filtro guarda la apariencia
  de lo que ve cuando está seguro y, una vuelta después, "recuerda" dónde era.
- Curvatura: las rectas se ven rectas desde cualquier punto de vista y las curvas, curvas.
  Evidencia débil (los teleobjetivos aplanan las curvas).

Todo es causal. Calibrado con la final 1500 m NCAA 2025 (1280x720); umbrales sin validar en otra
transmisión.
"""

from collections.abc import Callable, Sequence

import cv2
import numpy as np

from app.cv.zones.layout import zone_edges
from app.cv.zones.track import STANDARD, Track

# Zona útil del frame de TV (sin marcador de arriba ni franjas de abajo), fracción del alto.
ROI = (60 / 720, 520 / 720)
IGNORE_TV = [(0, 520, 1280, 720), (0, 0, 1280, 60)]  # franjas de gráficos en 1280x720

HIST_BINS = (16, 8)
HIST_SIZE = HIST_BINS[0] * HIST_BINS[1]
DESC_SIZE = 3 * (HIST_SIZE + 12)

Likelihood = Callable[[np.ndarray], np.ndarray]


# ------------------------------------------------------------------ cortes de plano
def shot_hist(frame: np.ndarray) -> np.ndarray:
    """Histograma (tono, saturación) normalizado de la zona útil, aplanado (HIST_SIZE,)."""
    h = frame.shape[0]
    crop = frame[int(ROI[0] * h) : int(ROI[1] * h)]
    small = cv2.resize(crop, (192, 92), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, list(HIST_BINS), [0, 180, 0, 256])
    return cv2.normalize(hist, hist).ravel()


class CutDetector:
    """True en el frame que empieza un plano nuevo (Bhattacharyya contra el frame anterior)."""

    def __init__(self, threshold: float = 0.19, min_gap_s: float = 0.5) -> None:
        self.threshold, self.min_gap_s = threshold, min_gap_s
        self._prev: np.ndarray | None = None
        self._last_cut = -np.inf

    def __call__(self, hist: np.ndarray, t: float) -> bool:
        h = np.asarray(hist, dtype=np.float32).reshape(HIST_BINS)
        cut = False
        if self._prev is not None:
            score = cv2.compareHist(self._prev, h, cv2.HISTCMP_BHATTACHARYYA)
            if score > self.threshold and t - self._last_cut >= self.min_gap_s:
                cut, self._last_cut = True, t
        self._prev = h
        return cut


# ------------------------------------------------------------------ apariencia
def descriptor(frame: np.ndarray) -> np.ndarray:
    """Color por bandas horizontales (tribuna / pista / pasto) + orientación de bordes por banda.

    Raíz cuadrada de histogramas normalizados: la distancia L2 equivale a Hellinger.
    """
    h = frame.shape[0]
    crop = frame[int(ROI[0] * h) : int(ROI[1] * h)]
    im = cv2.resize(crop, (320, 115), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    mag, ang = np.hypot(gx, gy), np.mod(np.arctan2(gy, gx), np.pi)
    out = []
    for band in np.array_split(np.arange(im.shape[0]), 3):
        sl = slice(band[0], band[-1] + 1)
        hc = cv2.calcHist([hsv[sl]], [0, 1], None, list(HIST_BINS), [0, 180, 0, 256]).ravel()
        out.append(np.sqrt(hc / hc.sum()))
        ho, _ = np.histogram(ang[sl], bins=12, range=(0, np.pi), weights=mag[sl])
        out.append(np.sqrt(ho / (ho.sum() + 1e-6)))
    return np.concatenate(out).astype(np.float32)


class CameraMemory:
    """Recuerdos (apariencia -> posición en la pista) y verosimilitud sobre s."""

    def __init__(
        self,
        track: Track = STANDARD,
        max_std: float = 12.0,
        k: int = 3,
        sigma_min: float = 12.0,
        floor: float = 0.15,
        accept: float = 0.75,
        scale: float = 0.6,
        min_age_s: float = 40.0,
        temper: float = 0.5,
    ) -> None:
        self.track = track
        self.max_std, self.k, self.sigma_min, self.floor = max_std, k, sigma_min, floor
        # Distancia absoluta (Hellinger) para "reconocer" un encuadre: un umbral relativo se
        # agranda con una sola cámara en memoria y termina reconociendo cualquier cosa.
        self.accept, self.scale = accept, scale
        # Solo se recuerda lo visto hace más de `min_age_s` (la vuelta anterior); si no, el más
        # parecido es el frame de hace un instante del mismo plano y congela el foco.
        self.min_age_s = min_age_s
        # Frames seguidos del mismo plano no son evidencia independiente: lik ** temper.
        self.temper = temper
        self.D: list[np.ndarray] = []
        self.S: list[float] = []
        self.SD: list[float] = []
        self.T: list[float] = []

    def add(self, desc: np.ndarray, s: float, s_std: float, t: float) -> bool:
        if s_std > self.max_std:
            return False
        self.D.append(desc)
        self.S.append(s % self.track.lap)
        self.SD.append(s_std)
        self.T.append(t)
        return True

    def match(self, desc: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """(s_k, sigma_k, peso_k) de los k recuerdos más parecidos, o None si no se reconoce."""
        old = (
            np.flatnonzero(np.array(self.T) <= t - self.min_age_s) if self.T else np.array([], int)
        )
        if len(old) < 5:
            return None
        d = np.full(len(self.D), np.inf)
        d[old] = np.sqrt(((np.stack([self.D[i] for i in old]) - desc) ** 2).sum(1))
        idx = np.argsort(d)[: self.k]
        if d[idx[0]] > self.accept:
            return None
        idx = idx[d[idx] <= self.accept]
        w = np.exp(-0.5 * (d[idx] / self.scale) ** 2)
        s = np.array(self.S)[idx]
        sig = np.maximum(self.sigma_min, np.array(self.SD)[idx] + 8.0)
        return s, sig, w / w.sum()

    def likelihood(self, desc: np.ndarray, t: float) -> Likelihood | None:
        m = self.match(desc, t)
        if m is None:
            return None
        s_k, sig_k, w_k = m
        lap = self.track.lap

        def lik(s: np.ndarray) -> np.ndarray:
            s = np.asarray(s, dtype=float)
            ds = (s[:, None] - s_k[None] + lap / 2) % lap - lap / 2
            return (self.floor + np.sum(w_k * np.exp(-0.5 * (ds / sig_k) ** 2), 1)) ** self.temper

        return lik


# ------------------------------------------------------------------ curvatura
def line_mask(frame: np.ndarray, ignore: Sequence[tuple[int, int, int, int]] = ()) -> np.ndarray:
    """Píxeles de líneas blancas pintadas sobre el tartán rojo."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    red = (((h < 14) | (h > 165)) & (s > 70) & (v > 60)).astype(np.uint8)
    white = ((s < 70) & (v > 165)).astype(np.uint8)
    # una línea es angosta y tiene rojo a ambos lados: blanco con rojo cerca en direcciones opuestas
    k = 6
    red_d = cv2.dilate(red, np.ones((3, 3), np.uint8))

    def near(dx: int, dy: int) -> np.ndarray:
        return np.roll(red_d, (dy, dx), axis=(0, 1))

    both_v = near(0, k) & near(0, -k)
    both_h = near(k, 0) & near(-k, 0)
    mask = (white & (both_v | both_h)).astype(np.uint8)
    for x1, y1, x2, y2 in ignore:
        mask[y1:y2, x1:x2] = 0
    return mask


def line_curvature(frame: np.ndarray, min_px: int = 120) -> dict:
    """Cuán curvas se ven las líneas pintadas.

    bend  flecha/cuerda ponderada por largo (0 = rectas; ~0,05+ = curva clara)
    chord largo total de líneas medidas (px en 1280x720): cuánto confiar
    n     número de trazos usados
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
        pts = np.stack([xs, ys], 1).astype(np.float64)
        c = pts.mean(0)
        _, sv, vt = np.linalg.svd(pts - c, full_matrices=False)
        u, v = (pts - c) @ vt[0], (pts - c) @ vt[1]
        chord = u.max() - u.min()
        if chord < 80 or sv[1] / max(sv[0], 1e-6) > 0.25:  # corto o "gordo" (persona, letrero)
            continue
        a = np.polyfit(u, v, 2)[0]
        bends.append(abs(a) * (chord / 2) ** 2 / chord)
        chords.append(chord)
    if not chords:
        return {"bend": 0.0, "chord": 0.0, "n": 0}
    arr = np.array(chords)
    return {
        "bend": float(np.sum(np.array(bends) * arr) / arr.sum()),
        "chord": float(arr.sum() / sx),
        "n": len(chords),
    }


def curvature_likelihood(
    bend: float,
    chord: float,
    n: int,
    track: Track = STANDARD,
    bend_curve: float = 0.012,
    width: float = 0.7,
    min_chord: float = 600.0,
    strength: float = 2.0,
) -> Likelihood | None:
    """P(observación | s): curva vs recta, con peso que crece con cuánta línea se vio.

    En la final: flecha/cuerda mediana 0,015 en curvas y 0,004 en rectas, con mucho solape
    (AUC 0,76); `strength` es la razón máxima curva:recta.
    """
    if n == 0:
        return None
    conf = min(1.0, chord / min_chord)
    z = (np.log(bend + 1e-4) - np.log(bend_curve)) / width
    p_curve = 1 / (1 + np.exp(-z))
    e = zone_edges(track)
    c1, c2 = (e[0], e[2]), (e[3], e[5])

    def lik(s: np.ndarray) -> np.ndarray:
        s = np.mod(np.asarray(s, dtype=float), track.lap)
        in_curve = ((s >= c1[0]) & (s < c1[1])) | ((s >= c2[0]) & (s < c2[1]))
        p = np.where(in_curve, p_curve, 1 - p_curve)
        return (1 - conf) + conf * (1 + (strength - 1) * p) / strength

    return lik
