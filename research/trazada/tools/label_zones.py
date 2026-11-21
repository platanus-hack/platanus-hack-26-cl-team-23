#!/usr/bin/env python
"""Etiquetar a mano en qué zona enfoca la cámara (verdad de terreno para evaluar).

Uso:
  python -m tools.label_zones --source data/ncaa1500.mp4 --out data/zones_labels.jsonl

Muestra un frame cada `--step` s entre la salida (`--t0`) y la llegada (`--t1`).
Teclas:
  1..6     zona y avanzar            espacio  misma zona que la muestra anterior y avanzar
  0        no se puede saber la zona (no se ve pista) y avanzar
  t f o r  tipo de plano: t=pista abierta, f=primer plano, o=otro (público, gráfico),
           r=repetición. Se mantiene en las muestras siguientes hasta que lo cambies.
  c        marcar/desmarcar "hubo corte de plano desde la muestra anterior"
  a / d    atrás / adelante sin etiquetar
  s        guardar         q  guardar y salir
Retoma un archivo existente. Arriba a la derecha va el frame anterior, para ver cortes.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from trazada.geometry import STANDARD as T
from trazada.zones import NAMES, zone_edges

SHOTS = {ord("t"): "pista", ord("f"): "primer_plano", ord("o"): "otro", ord("r"): "repeticion"}


def legend(size=(260, 150)) -> np.ndarray:
    """Óvalo cenital con las zonas numeradas (meta a la derecha de la recta de abajo)."""
    w, h = size
    img = np.full((h, w, 3), 40, np.uint8)
    scale = (w - 30) / (T.straight + 2 * (T.radius + 10))
    edges = zone_edges(T)
    cols = [(80, 80, 230), (80, 160, 230), (80, 220, 120), (230, 160, 80), (230, 80, 160), (200, 200, 200)]
    for z in range(6):
        s = np.linspace(edges[z], edges[z + 1], 40)
        x, y = T.track_to_world(s, np.full_like(s, 4.0))
        pts = np.stack([w / 2 + x * scale, h / 2 - y * scale], 1).astype(np.int32)
        cv2.polylines(img, [pts], False, cols[z], 6)
        xm, ym = T.track_to_world((edges[z] + edges[z + 1]) / 2, 15.0)
        cv2.putText(img, str(z + 1), (int(w / 2 + xm * scale) - 6, int(h / 2 - ym * scale) + 6), 0, 0.6, cols[z], 2)
    x, y = T.track_to_world(0.0, np.array([0, 9.0]))
    cv2.line(img, (int(w / 2 + x[0] * scale), int(h / 2 - y[0] * scale)),
             (int(w / 2 + x[1] * scale), int(h / 2 - y[1] * scale)), (255, 255, 255), 2)
    cv2.putText(img, "meta", (int(w / 2 + x[1] * scale) - 20, h - 4), 0, 0.4, (255, 255, 255), 1)
    cv2.putText(img, "<- sentido antihorario", (5, 14), 0, 0.4, (200, 200, 200), 1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/ncaa1500.mp4")
    ap.add_argument("--out", default="data/zones_labels.jsonl")
    ap.add_argument("--t0", type=float, default=58.7, help="segundo del video en que suena el disparo")
    ap.add_argument("--t1", type=float, default=286.5, help="segundo del video de la llegada")
    ap.add_argument("--step", type=float, default=0.5)
    a = ap.parse_args()

    cap = cv2.VideoCapture(a.source)
    fps = cap.get(cv2.CAP_PROP_FPS)
    times = np.round(np.arange(a.t0, a.t1 + 1e-9, a.step), 3)
    labels = {}
    out = Path(a.out)
    if out.exists():
        for line in out.open():
            r = json.loads(line)
            labels[round(r["t_video"], 3)] = r

    def save():
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as f:
            for t in times:
                if float(t) in labels:
                    f.write(json.dumps(labels[float(t)]) + "\n")
        print(f"guardado: {len(labels)}/{len(times)} muestras en {out}")

    def frame_at(t):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, f = cap.read()
        return f if ok else np.zeros((720, 1280, 3), np.uint8)

    leg = legend()
    i = next((k for k, t in enumerate(times) if float(t) not in labels), 0)
    shot = "pista"
    cv2.namedWindow("zonas", cv2.WINDOW_NORMAL)
    while True:
        t = float(times[i])
        cur = labels.get(t, {})
        prev = labels.get(float(times[i - 1]), {}) if i > 0 else {}
        shot = cur.get("shot", shot)
        img = frame_at(t).copy()
        if i > 0:
            pv = cv2.resize(frame_at(float(times[i - 1])), (320, 180))
            img[0:180, -320:] = pv
            cv2.rectangle(img, (img.shape[1] - 320, 0), (img.shape[1] - 1, 179), (255, 255, 255), 1)
        img[-leg.shape[0]:, :leg.shape[1]] = leg
        z = cur.get("zone")
        txt = (f"{i + 1}/{len(times)}  video {t:.1f}s  carrera {t - a.t0:.1f}s  |  zona: "
               f"{z if z else '-'} {NAMES.get(z, '')}  |  plano: {shot}  |  corte: {'SI' if cur.get('cut') else 'no'}"
               f"  |  anterior: {prev.get('zone', '-')}")
        cv2.rectangle(img, (0, 0), (img.shape[1] - 330, 30), (0, 0, 0), -1)
        cv2.putText(img, txt, (8, 21), 0, 0.55, (0, 255, 255), 1)
        cv2.imshow("zonas", img)
        k = cv2.waitKey(0) & 0xFF

        def put(zone):
            labels[t] = {"t_video": t, "t_race": round(t - a.t0, 3), "zone": zone, "shot": shot,
                         "cut": bool(cur.get("cut", False))}

        if k in (ord("q"), 27):
            save()
            break
        elif k == ord("s"):
            save()
        elif ord("1") <= k <= ord("6"):
            put(k - ord("0")); i = min(i + 1, len(times) - 1)
        elif k == ord("0"):
            put(None); i = min(i + 1, len(times) - 1)
        elif k == ord(" ") and prev:
            put(prev.get("zone")); i = min(i + 1, len(times) - 1)
        elif k in SHOTS:
            shot = SHOTS[k]
            if t in labels:
                labels[t]["shot"] = shot
        elif k == ord("c"):
            cur = labels.setdefault(t, {"t_video": t, "t_race": round(t - a.t0, 3), "zone": None, "shot": shot, "cut": False})
            cur["cut"] = not cur.get("cut", False)
        elif k == ord("a"):
            i = max(i - 1, 0)
        elif k == ord("d"):
            i = min(i + 1, len(times) - 1)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
