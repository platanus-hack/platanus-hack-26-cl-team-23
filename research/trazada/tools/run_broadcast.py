#!/usr/bin/env python
"""Posición de cada corredor en un tramo de video de TV (cámara que panea y hace zoom).

Parte de una calibración inicial (out/cal156.json, de tools/fit_broadcast + refine) y la sigue
frame a frame con HomographyTracker.
"""
import argparse, json, time
from collections import defaultdict, deque
import cv2, numpy as np
from trazada.broadcast import HomographyTracker
from trazada.calibration import Calibration
from trazada.geometry import Track
from trazada.pipeline import RunnerLocator
from trazada.viz import TopView, draw_runners, draw_track_overlay

IGNORE = [(0, 640, 1280, 720), (990, 560, 1220, 640), (50, 35, 235, 62)]

ap = argparse.ArgumentParser()
ap.add_argument("--video", default="data/ncaa1500.mp4")
ap.add_argument("--calib", default="out/cal156_gauge.json")
ap.add_argument("--t0", type=float, default=156.0)
ap.add_argument("--t1", type=float, default=163.0)
ap.add_argument("--model", default="yolo26s.pt")
ap.add_argument("--out", default="out/broadcast")
a = ap.parse_args()

T = Track(lanes=9)
cal = Calibration.load(a.calib)
cam = HomographyTracker(cal.H, T, ignore=IGNORE, correct=False)  # en esta toma la corrección por líneas diverge
loc = RunnerLocator(cal, model=a.model, tracker="botsort_broadcast.yaml", imgsz=1280, conf=0.3, track=T,
                    calib_provider=lambda f, b: cam.update(f, b))
loc.max_dd, loc.max_ds = 0.9, 3.0

cap = cv2.VideoCapture(a.video); fps = cap.get(5)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(a.t0 * fps)))
n = int((a.t1 - a.t0) * fps)
vw = None; jl = open(a.out + ".jsonl", "w")
cam_log = []
trails = defaultdict(lambda: deque(maxlen=240))
STEP = 2  # el video es de 30 fps duplicado a 60: cada frame aparece dos veces
for i in range(0, n, STEP):
    ok, f = cap.read(); cap.grab()
    if not ok: break
    t = i / fps
    t_a = time.perf_counter()
    rs = loc.process(f, t)
    dt = time.perf_counter() - t_a
    cam_log.append((t, cam.err, cam.n_px, dt))
    jl.write(json.dumps({"t": round(t, 3), "frame": i, "cam_err_m": cam.err, "runners": [r.to_json() for r in rs]}) + "\n")
    v = f.copy(); draw_track_overlay(v, loc.calib, T)
    for r in rs: trails[r.id].append((r.x, r.y))
    draw_runners(v, rs)
    cv2.putText(v, f"t={a.t0 + t:6.2f}s  {len(rs)} corredores", (12, 690), 0, 0.7, (255, 255, 255), 2)
    top = TopView(Calibration(loc.calib.H, (1280, 720), world_pts=[[ -60, -50], [-20, -30], [ -80, 10], [-30, 20]]), T, size=(400, 720), pad_m=3)
    out = np.hstack([v, top.render(rs, trails)])
    if vw is None: vw = cv2.VideoWriter(a.out + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps / STEP, (out.shape[1], out.shape[0]))
    vw.write(out)
vw.release(); jl.close()
L = np.array(cam_log)
print(f"{len(L)} frames · error de cámara mediano {100*np.nanmedian(L[:,1]):.1f} cm (p90 {100*np.nanpercentile(L[:,1],90):.1f}) · {1000*L[:,3].mean():.0f} ms/frame")
