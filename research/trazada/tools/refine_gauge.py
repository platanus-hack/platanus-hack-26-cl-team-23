#!/usr/bin/env python
"""Fija el "deslizamiento a lo largo de la pista" de la calibración inicial usando varios frames.

En un frame que solo muestra curva, girar la pista sobre el centro de la curva no cambia las líneas:
no se sabe dónde empieza la recta. Se sigue la cámara con ECC unos segundos, se llevan las líneas
de todos esos frames al frame inicial y se busca el giro (y el ajuste fino) que mejor las explica.
"""
import argparse
import cv2, numpy as np
from ultralytics import YOLO
from trazada.broadcast import HomographyTracker, line_mask, grass_pixels, refine_homography_lines
from trazada.calibration import Calibration
from trazada.geometry import Track

IGNORE = [(0, 640, 1280, 720), (990, 560, 1220, 640), (50, 35, 235, 62)]
ap = argparse.ArgumentParser()
ap.add_argument("--video", default="data/ncaa1500.mp4")
ap.add_argument("--calib", default="out/cal156.json")
ap.add_argument("--f0", type=int, default=9360)
ap.add_argument("--secs", type=float, default=3.5)
ap.add_argument("--out", default="out/cal156_gauge.json")
a = ap.parse_args()

T = Track(lanes=9); W_ = T.lane_width
cal = Calibration.load(a.calib); H0 = cal.H / cal.H[2, 2]
tr = HomographyTracker(H0, T, ignore=IGNORE, correct=False)
yolo = YOLO("yolo26n.pt")
c = cv2.VideoCapture(a.video); c.set(cv2.CAP_PROP_POS_FRAMES, a.f0)
Q, Gq = [], []
rng = np.random.default_rng(0)
for i in range(0, int(a.secs * 60), 2):
    ok, f = c.read(); c.grab()
    b = yolo(f, classes=[0], verbose=False)[0].boxes.xyxy.cpu().numpy()
    tr.update(f, b)
    if i % 10:
        continue
    back = np.linalg.inv(H0) @ tr.H          # píxel en t -> píxel en el frame inicial
    ys, xs = np.nonzero(line_mask(f, b, IGNORE))
    sel = rng.choice(len(xs), min(800, len(xs)), replace=False)
    P = np.c_[xs[sel], ys[sel]].astype(float)
    Q.append(cv2.perspectiveTransform(P.reshape(-1, 1, 2), back).reshape(-1, 2))
    g = grass_pixels(f, IGNORE, b, n=200)
    if len(g):
        Gq.append(cv2.perspectiveTransform(g.reshape(-1, 1, 2), back).reshape(-1, 2))
Q, Gq = np.vstack(Q), np.vstack(Gq)
print(f"{len(Q)} píxeles de línea y {len(Gq)} de pasto de {i // 10 + 1} frames")

cx = -T.straight / 2  # centro de la curva 2

def rot(delta_m):
    th = delta_m / T.r_meas
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    Tm = np.array([[1, 0, cx], [0, 1, 0], [0, 0, 1.0]])
    return Tm @ R @ np.linalg.inv(Tm)

def cost(H):
    w = cv2.perspectiveTransform(Q.reshape(-1, 1, 2), H).reshape(-1, 2)
    _, d = T.world_to_track(w[:, 0], w[:, 1])
    k = np.clip(np.round(d / W_), 0, T.lanes)
    r = np.minimum(np.abs(d - k * W_), 0.35)
    wg = cv2.perspectiveTransform(Gq.reshape(-1, 1, 2), H).reshape(-1, 2)
    _, dg = T.world_to_track(wg[:, 0], wg[:, 1])
    return r.mean() + 2 * np.maximum(0, dg + 0.15).clip(max=1).mean()

deltas = np.arange(-25, 25.01, 0.25)
costs = [cost(rot(dl) @ H0) for dl in deltas]
best = deltas[int(np.argmin(costs))]
print("costo sin corregir %.3f · mejor giro %+.2f m (costo %.3f)" % (cost(H0), best, min(costs)))
H = rot(best) @ H0
for _ in range(3):
    w = cv2.perspectiveTransform(Q.reshape(-1, 1, 2), H).reshape(-1, 2)
    _, d = T.world_to_track(w[:, 0], w[:, 1])
    k = np.round(d / W_); okm = (np.abs(d - k * W_) < 0.25) & (k >= 0) & (k <= T.lanes)
    pix = {int(kk): Q[okm & (k == kk)] for kk in np.unique(k[okm])}
    H, med, _ = refine_homography_lines(H, pix, T, reg=0.02, grass=Gq)
print("después del ajuste fino: costo %.3f · error mediano de líneas %.1f cm" % (cost(H), 100 * med))
Calibration(H / H[2, 2], cal.image_size).save(a.out)
