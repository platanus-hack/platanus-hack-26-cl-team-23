import cv2
import numpy as np

# Pista de tartán burdeos/ladrillo en HSV de OpenCV (H 0-180). [inferido] de NCCA.mp4;
# recalibrar si se usa otra pista (azul, verde, etc.).
_HUE_LOW = 14
_HUE_HIGH = 165
_MIN_SAT = 70
_MIN_VAL = 60


def on_track_fraction(hsv: np.ndarray, box: list[float]) -> float:
    """Fracción de píxeles color pista justo bajo los pies de una caja.

    No depende de la cámara: un corredor tiene los pies sobre la pista; el público,
    los oficiales y los gráficos no.
    """
    height, width = hsv.shape[:2]
    x1, _, x2, y2 = box[:4]
    cx = (x1 + x2) / 2
    half = max(20.0, x2 - x1) * 0.75
    xa, xb = int(max(0, cx - half)), int(min(width - 1, cx + half))
    ya, yb = int(max(0, y2 - 6)), int(min(height - 1, y2 + 14))
    if xb <= xa or yb <= ya:
        return 0.0
    patch = hsv[ya:yb, xa:xb].reshape(-1, 3).astype(int)
    hue, sat, val = patch[:, 0], patch[:, 1], patch[:, 2]
    mask = ((hue <= _HUE_LOW) | (hue >= _HUE_HIGH)) & (sat >= _MIN_SAT) & (val >= _MIN_VAL)
    return float(mask.mean())


def to_hsv(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
