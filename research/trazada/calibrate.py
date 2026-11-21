#!/usr/bin/env python
"""Calibra la cámara contra la pista haciendo clic en puntos conocidos.

Uso:
  python calibrate.py --source video.mp4 --out calib.json
  python calibrate.py --source 0 --out calib.json            # cámara / iPhone (Continuity Camera)
  python calibrate.py --source video.mp4 --points pts.json   # sin interacción: [[u, v, s, d], ...]

En la ventana:
  clic      marca un punto; en la terminal escribes sus coordenadas de pista "s d"
            (s = metros desde la meta en sentido de carrera, d = metros desde el bordillo)
            o "x y" en metros del mundo si usaste --world.
  u         deshace el último punto
  c         calcula y muestra las líneas de pista reproyectadas (deben calzar con las reales)
  s         guarda y sale          q   sale sin guardar

Puntos fáciles de usar: cruces de líneas de pista con la meta (s = 0) o con otras líneas
transversales pintadas (salidas, zonas de relevo) cuya s conozcas. d = k * 1.22 sobre la
línea k (0 = bordillo). Usa >= 4 puntos repartidos, no todos en una línea; ideal 6-10.
"""
import argparse
import json

import cv2
import numpy as np

from trazada.calibration import fit, track_pts_to_world
from trazada.geometry import STANDARD
from trazada.viz import draw_track_overlay


def first_frame(src: str, skip: int):
    cap = cv2.VideoCapture(int(src) if src.isdigit() else src)
    for _ in range(max(1, skip if not src.isdigit() else 15)):  # las cámaras tardan en ajustar exposición
        ok, f = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"No se pudo leer un frame de {src}")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", default="calib.json")
    ap.add_argument("--frame", type=int, default=1, help="frame del video a usar")
    ap.add_argument("--world", action="store_true", help="ingresar x y en metros del mundo en vez de s d")
    ap.add_argument("--points", help="JSON con [[u, v, a, b], ...] para calibrar sin interacción")
    a = ap.parse_args()

    img = first_frame(a.source, a.frame)
    h, w = img.shape[:2]
    to_world = (lambda p: np.asarray(p, float)) if a.world else (lambda p: track_pts_to_world(p, STANDARD))

    if a.points:
        rows = np.asarray(json.load(open(a.points)), float)
        cal = fit(rows[:, :2], to_world(rows[:, 2:4]), (w, h))
        cal.save(a.out)
        print(f"Guardado {a.out} · {len(rows)} puntos · error RMS {cal.rms_m:.3f} m")
        return

    img_pts, ref_pts, preview, pending = [], [], None, []
    cv2.namedWindow("calibrar", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("calibrar", lambda ev, x, y, *_: pending.append((x, y)) if ev == cv2.EVENT_LBUTTONDOWN else None)

    while True:
        view = (preview if preview is not None else img).copy()
        for i, (p, q) in enumerate(zip(img_pts, ref_pts)):
            cv2.circle(view, p, 5, (0, 255, 255), -1)
            cv2.putText(view, f"{i + 1}: {q[0]:g},{q[1]:g}", (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow("calibrar", view)
        k = cv2.waitKey(30) & 0xFF
        if pending:
            p = pending.pop(0)
            cv2.circle(view, p, 6, (0, 0, 255), 2)
            cv2.imshow("calibrar", view)
            cv2.waitKey(1)
            raw = input(f"Punto {len(img_pts) + 1} en {p} -> {'x y' if a.world else 's d'} (vacío = descartar): ").strip()
            if raw:
                try:
                    q = tuple(float(v) for v in raw.replace(",", " ").split()[:2])
                    img_pts.append(p)
                    ref_pts.append(q)
                    preview = None
                except ValueError:
                    print("  formato: dos números, p. ej. '0 2.44'")
        elif k == ord("u") and img_pts:
            img_pts.pop(); ref_pts.pop(); preview = None
        elif k in (ord("c"), ord("s")):
            if len(img_pts) < 4:
                print("Faltan puntos: mínimo 4")
                continue
            cal = fit(img_pts, to_world(ref_pts), (w, h))
            print(f"Error RMS de reproyección: {cal.rms_m:.3f} m  ({'bien' if cal.rms_m < 0.15 else 'revisa los puntos'})")
            preview = img.copy()
            draw_track_overlay(preview, cal)
            if k == ord("s"):
                cal.save(a.out)
                json.dump([[*p, *q] for p, q in zip(img_pts, ref_pts)], open(a.out.replace(".json", "_points.json"), "w"))
                print(f"Guardado {a.out}")
                break
        elif k == ord("q"):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
