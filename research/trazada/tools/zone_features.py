#!/usr/bin/env python
"""Recorre el video una vez y guarda, por muestra, la evidencia visual para el filtro de zonas.

Uso: python -m tools.zone_features --source data/ncaa1500.mp4 --t0 58.7 --t1 286.0 --out out/zone_feats.npz

Por muestra (cada `--step` s de carrera): si hubo corte desde la anterior (detector causal sobre
todos los frames), el descriptor de apariencia y la curvatura de las líneas. Todo es causal; se
guarda para poder probar variantes del filtro sin decodificar el video cada vez.
"""
import argparse
import time

import cv2
import numpy as np

from trazada.evidence import descriptor, line_curvature
from trazada.shots import ShotDetector


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/ncaa1500.mp4")
    ap.add_argument("--t0", type=float, default=58.7, help="segundo del video del disparo")
    ap.add_argument("--t1", type=float, default=286.0)
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--out", default="out/zone_feats.npz")
    a = ap.parse_args()

    cap = cv2.VideoCapture(a.source)
    fps = cap.get(cv2.CAP_PROP_FPS)
    i = int(round(a.t0 * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    sd = ShotDetector()
    next_t, cut_pending, cuts = 0.0, False, []
    rows = {k: [] for k in ("t", "cut", "desc", "bend", "chord", "n")}
    tic = time.time()
    while True:
        ok, f = cap.read()
        if not ok:
            break
        t = i / fps - a.t0
        if t > a.t1 - a.t0 + 1e-6:
            break
        if i % 2 == 0 and sd(f, t):   # el video es 30 fps duplicado a 60
            cut_pending = True
            cuts.append(round(t, 2))
        if t >= next_t - 0.5 / fps:
            c = line_curvature(f)
            rows["t"].append(round(next_t, 3)); rows["cut"].append(cut_pending)
            rows["desc"].append(descriptor(f)); rows["bend"].append(c["bend"])
            rows["chord"].append(c["chord"]); rows["n"].append(c["n"])
            cut_pending = False
            next_t += a.step
        i += 1
    np.savez_compressed(a.out, **{k: np.array(v) for k, v in rows.items()}, cuts=np.array(cuts))
    print(f"{len(rows['t'])} muestras, {len(cuts)} cortes {cuts}  ({time.time() - tic:.0f} s) -> {a.out}")


if __name__ == "__main__":
    main()
