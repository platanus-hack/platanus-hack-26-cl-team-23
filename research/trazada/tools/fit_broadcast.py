#!/usr/bin/env python
"""Calibra una cámara de TV en un frame a partir de líneas de pista etiquetadas a mano."""
import json
import cv2, numpy as np
from trazada.broadcast import labeled_pixels, search_labeled, to_calibration
from trazada.geometry import Track
from trazada.viz import draw_track_overlay

# Frame 156.0 s: componentes de out/comps.jpg agrupados por línea (0 = la más interior)
GROUPS = {0: [82, 63, 51, 45, 35, 20, 7], 1: [80, 6], 2: [59, 5], 3: [30, 32, 4], 4: [3], 5: [14, 2], 6: [1]}
track = Track(lanes=9)
f = cv2.imread("out/full_156.jpg")
size = (f.shape[1], f.shape[0])
pix = labeled_pixels(np.load("out/comps156.npy"), GROUPS)
p, err = search_labeled(pix, track, (150, 400), size, cam_box=[(70, 240), (-90, 30), (3, 80)],
                        target_sd_box=[(220, 360), (0, 11)], f_range=(6000, 90000), n=100_000)
json.dump({"p": list(map(float, p)), "t": 156.0, "err_px": err}, open("out/cam0.json", "w"))
v = f.copy(); draw_track_overlay(v, to_calibration(p, size), track); cv2.imwrite("out/cam0.jpg", v)
