#!/usr/bin/env python
"""Genera un video sintético con verdad de terreno para probar el pipeline sin ir a la pista.

Pinta la pista vista desde una "tribuna" con una homografía conocida y pega recortes de
personas reales (de las imágenes de ejemplo de Ultralytics) corriendo por pistas conocidas,
con escala según la perspectiva. Guarda:
  out/synth.mp4            el video
  out/synth_truth.jsonl    posición real (s, d) de cada corredor por frame
  out/synth_points.json    puntos de calibración [[u, v, s, d], ...] para calibrate.py --points
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np

from trazada.geometry import STANDARD as T

OUT = Path("out")
W, H, FPS, DUR = 1280, 720, 30, 7.0

# cámara: rectángulo del mundo -> trapecio en la imagen (cerca = abajo)
WORLD_Q = np.float32([[32, -50], [80, -50], [80, -14], [32, -14]])
IMG_Q = np.float32([[-150, 760], [1430, 760], [1080, 40], [180, 40]])
G = cv2.getPerspectiveTransform(WORLD_Q, IMG_Q)  # mundo -> imagen


def proj(xy):
    return cv2.perspectiveTransform(np.float64(xy).reshape(-1, 1, 2), G).reshape(-1, 2)


def background():
    ppm, x0, y0, x1, y1 = 20, 10, -60, 100, 20
    tw, th = int((x1 - x0) * ppm), int((y1 - y0) * ppm)
    tex = np.full((th, tw, 3), (60, 105, 70), np.uint8)
    to_tex = lambda x, y: np.c_[(x - x0) * ppm, (y1 - y) * ppm]
    s = np.arange(0, T.lap + 0.2, 0.2)
    xo, yo = T.track_to_world(s, np.full_like(s, T.lanes * T.lane_width))
    xi, yi = T.track_to_world(s, np.zeros_like(s))
    cv2.fillPoly(tex, [np.int32(np.vstack([to_tex(xo, yo), to_tex(xi, yi)[::-1]]))], (60, 70, 175))
    for k in range(T.lanes + 1):
        x, y = T.track_to_world(s, np.full_like(s, k * T.lane_width))
        cv2.polylines(tex, [np.int32(to_tex(x, y))], False, (240, 240, 240), 3 if k == 0 else 2, cv2.LINE_AA)
    x, y = T.track_to_world(np.zeros(2), np.array([0, T.lanes * T.lane_width]))
    cv2.line(tex, *[tuple(map(int, p)) for p in to_tex(x, y)], (240, 240, 240), 4)  # meta
    A = np.array([[ppm, 0, -x0 * ppm], [0, -ppm, y1 * ppm], [0, 0, 1]], float)  # mundo -> textura
    bg = cv2.warpPerspective(tex, G @ np.linalg.inv(A), (W, H), borderValue=(110, 120, 130))
    return bg


def person_crops():
    from ultralytics import YOLO
    import ultralytics
    assets = Path(ultralytics.__file__).parent / "assets"
    m = YOLO("yolo26n.pt")
    crops = []
    for name in ("bus.jpg", "zidane.jpg"):
        img = cv2.imread(str(assets / name))
        r = m(img, classes=[0], verbose=False)[0]
        for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
            if c > 0.6 and (y2 - y1) > 1.6 * (x2 - x1):  # personas de cuerpo entero
                crops.append(img[int(y1):int(y2), int(x1):int(x2)].copy())
    return crops


def d_profile(kind, s):
    if kind == "out":  # se abre de pista 1 a pista 3 al entrar a la curva
        u = np.clip(T.ds_wrap(385, s) / 12.0, 0, 1)
        return 0.4 + (2.9 - 0.4) * (u * u * (3 - 2 * u))
    return kind


def main():
    OUT.mkdir(exist_ok=True)
    bg = background()
    crops = person_crops()
    print(f"{len(crops)} recortes de personas")
    runners = [  # id, s0, v (m/s de progreso), d
        dict(id=1, s0=386.0, v=6.6, d=0.45),
        dict(id=2, s0=383.5, v=6.6, d=1.75),
        dict(id=3, s0=380.0, v=7.3, d="out"),
        dict(id=4, s0=378.0, v=6.4, d=0.5),
    ]
    vw = cv2.VideoWriter(str(OUT / "synth.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    truth = open(OUT / "synth_truth.jsonl", "w")
    for k in range(int(DUR * FPS)):
        t = k / FPS
        frame = bg.copy()
        rows = []
        for i, r in enumerate(runners):
            s = (r["s0"] + r["v"] * t) % T.lap
            d = d_profile(r["d"], s)
            x, y = T.track_to_world(s, d)
            (u, v), (u2, _) = proj([[x, y], [x + 1, y]])
            px_per_m = max(abs(u2 - u), 1e-3)
            rows.append((v, i, s, d, u, v, px_per_m))
        for v_, i, s, d, u, v, ppm in sorted(rows):  # más lejos primero
            c = crops[i % len(crops)]
            bob = 1 + 0.03 * math.sin(2 * math.pi * 3 * (k / FPS) + i)  # "zancada"
            h = int(1.75 * ppm * 1.15 * bob)
            w = max(4, int(c.shape[1] * h / c.shape[0]))
            if h < 12:
                continue
            c2 = cv2.resize(c, (w, h))
            x1, y1 = int(u - w / 2), int(v - h)
            xa, ya, xb, yb = max(0, x1), max(0, y1), min(W, x1 + w), min(H, y1 + h)
            if xa < xb and ya < yb:
                frame[ya:yb, xa:xb] = c2[ya - y1:yb - y1, xa - x1:xb - x1]
            truth.write(json.dumps({"frame": k, "t": t, "id": runners[i]["id"], "s": s, "d": d}) + "\n")
        vw.write(frame)
    vw.release()
    truth.close()

    # puntos de calibración: cruces de líneas de pista con transversales conocidas
    sd = [(s, k * T.lane_width) for s in (380, 0, 15, 30) for k in (0, 4, 8)]
    x, y = T.track_to_world(np.array([p[0] for p in sd]), np.array([p[1] for p in sd]))
    uv = proj(np.c_[x, y])
    rng = np.random.default_rng(1)
    uv += rng.normal(0, 1.5, uv.shape)  # error de clic de ~1.5 px
    pts = [[float(u), float(v), s, d] for (u, v), (s, d) in zip(uv, sd) if 0 <= u < W and 0 <= v < H]
    json.dump(pts, open(OUT / "synth_points.json", "w"), indent=1)
    print(f"Video: {OUT/'synth.mp4'} · {len(pts)} puntos de calibración")


if __name__ == "__main__":
    main()
