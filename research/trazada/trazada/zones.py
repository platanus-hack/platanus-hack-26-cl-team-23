"""Las 6 zonas de la pista y lo que el reglamento dice de cada carrera.

    Z1 curva 1, entrada   Z2 curva 1, salida   Z3 recta opuesta
    Z4 curva 2, entrada   Z5 curva 2, salida   Z6 recta principal (termina en la meta)

Todo en `s` (metros desde la meta en sentido de carrera, ver geometry.py). Cada curva se
parte en su punto medio (el vértice), así las 4 mitades miden lo mismo.
"""
from __future__ import annotations

import numpy as np

from .geometry import STANDARD, Track

NAMES = {1: "curva 1 entrada", 2: "curva 1 salida", 3: "recta opuesta",
         4: "curva 2 entrada", 5: "curva 2 salida", 6: "recta principal"}

# Velocidad media plausible por prueba (m/s, campeonato masculino de alto nivel, rango amplio).
# Sale del rango de marcas típicas de una final; no usa el tiempo real de la carrera analizada.
PACE = {800: (6.9, 7.9), 1500: (6.3, 7.1), 1609: (6.2, 7.0), 3000: (5.9, 6.6),
        5000: (5.7, 6.5), 10000: (5.5, 6.3)}


def zone_edges(track: Track = STANDARD) -> np.ndarray:
    """Límites en s: [0, c/2, c, c+l, c+l+c/2, 2c+l, 400]."""
    c, l = track.curve_len, track.straight
    return np.array([0, c / 2, c, c + l, c + l + c / 2, 2 * c + l, track.lap])


def zone_of(s, track: Track = STANDARD):
    """Zona 1..6 de una posición (escalar o array). Acepta s fuera de [0, 400)."""
    s = np.mod(np.asarray(s, dtype=float), track.lap)
    z = np.searchsorted(zone_edges(track)[1:-1], s, side="right") + 1
    return int(z) if z.ndim == 0 else z


def start_s(distance: float, track: Track = STANDARD) -> float:
    """Dónde parte una carrera de fondo/medio fondo: toda carrera termina en la meta (s = 0),
    así que la salida está `distance` metros antes. 1500 -> s = 100 (en Z2), 5000 -> 200 (inicio
    de la curva 2), 800/10000 -> en la meta. Para el 800 con calles escalonadas es la línea de la
    calle 1."""
    return float((-distance) % track.lap)


def zone_sequence(distance: float, track: Track = STANDARD) -> list[int]:
    """Orden en que el líder pasa por las zonas, de la salida a la meta."""
    edges = zone_edges(track)
    s0 = start_s(distance, track)
    seq, x = [zone_of(s0, track)], 0.0
    while True:
        s = (s0 + x) % track.lap
        nxt = edges[edges > s + 1e-9][0]   # siguiente límite
        x += nxt - s
        if x >= distance - 1e-6:
            return seq
        seq.append(zone_of(s0 + x + 1e-6, track))
