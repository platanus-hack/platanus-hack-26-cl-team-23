"""Las 6 zonas de la pista y lo que el reglamento dice de cada carrera.

    Z1 curva 1, entrada   Z2 curva 1, salida   Z3 recta opuesta
    Z4 curva 2, entrada   Z5 curva 2, salida   Z6 recta principal (termina en la meta)

Cada curva se parte en su punto medio, así las 4 mitades miden lo mismo.
"""

import numpy as np

from app.cv.zones.track import STANDARD, Track

NAMES = {
    1: "curva 1 entrada",
    2: "curva 1 salida",
    3: "recta opuesta",
    4: "curva 2 entrada",
    5: "curva 2 salida",
    6: "recta principal",
}

# Velocidad media plausible por prueba (m/s, final de campeonato masculino, rango amplio).
PACE = {
    800: (6.9, 7.9),
    1500: (6.3, 7.1),
    1609: (6.2, 7.0),
    3000: (5.9, 6.6),
    5000: (5.7, 6.5),
    10000: (5.5, 6.3),
}
DEFAULT_PACE = (5.5, 8.0)


def zone_edges(track: Track = STANDARD) -> np.ndarray:
    """Límites en s: [0, c/2, c, c+l, c+l+c/2, 2c+l, 400]."""
    c, length = track.curve_len, track.straight
    return np.array([0, c / 2, c, c + length, c + length + c / 2, 2 * c + length, track.lap])


def zone_of(s: float | np.ndarray, track: Track = STANDARD) -> int | np.ndarray:
    """Zona 1..6 de una posición (escalar o array); acepta s fuera de [0, 400)."""
    arr = np.mod(np.asarray(s, dtype=float), track.lap)
    zone = np.searchsorted(zone_edges(track)[1:-1], arr, side="right") + 1
    return int(zone) if zone.ndim == 0 else zone


def start_s(distance: float, track: Track = STANDARD) -> float:
    """Dónde parte la carrera: toda carrera termina en la meta, así que sale `distance` m antes.

    1500 -> s = 100 (Z2); 5000 -> 200 (inicio de la curva 2); 800 y 10000 -> en la meta.
    """
    return float((-distance) % track.lap)
