#!/usr/bin/env python
"""Video de la carrera con el pronóstico de zona impreso encima, calculado en línea.

Uso:
  python -m tools.render_zones --source data/ncaa1500.mp4 --out out/zonas.mp4 [--labels data/zones_labels.jsonl]

Recorre el video en orden y en cada instante usa solo lo visto hasta ahí (igual que en vivo):
detector de cortes en cada frame, evidencia (memoria de cámaras + curvatura) cada 0,5 s y el
filtro de partículas avanzando con el reloj de carrera. El panel muestra:
  - óvalo cenital con la probabilidad de cada zona (más intenso = más probable), la posición
    estimada del foco y su incertidumbre;
  - zona reportada (con histéresis), metros recorridos / faltantes y vuelta;
  - barras P(Z1..Z6) y avisos: CORTE, cámara reconocida, líneas curvas/rectas.
Con --labels agrega la etiqueta borrador para comparar a ojo.

OpenCV escribe H.264 a tasa alta (~1,6 MB/s). En macOS se comprime después con:
  python -m tools.render_zones --out out/zonas_raw.mp4
  avconvert -p Preset1280x720 -s out/zonas_raw.mp4 -o out/zonas.mp4
"""
import argparse
import json
import time

import cv2
import numpy as np

from trazada.evidence import CameraMemory, curvature_likelihood, descriptor, line_curvature
from trazada.geometry import STANDARD as T
from trazada.shots import ShotDetector
from trazada.zone_filter import ZoneFilter, ZoneReporter
from trazada.zones import NAMES, start_s, zone_edges

# BGR, mismos colores que la leyenda de label_zones
COLS = [(80, 80, 230), (80, 160, 230), (80, 220, 120), (230, 160, 80), (230, 80, 160), (200, 200, 200)]
PW, PH = 380, 300   # panel


def _oval_px(s, d, scale, cx, cy):
    x, y = T.track_to_world(s, d)
    return np.stack([cx + np.asarray(x) * scale, cy - np.asarray(y) * scale], -1)


def draw_panel(est, probs, reported, info, truth=None):
    p = np.zeros((PH, PW, 3), np.uint8)
    p[:] = (25, 25, 25)
    cv2.putText(p, "TRAZADA - zona enfocada", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    # ---- óvalo con probabilidades
    cx, cy, scale = 120, 125, 210 / (T.straight + 2 * (T.radius + 12))
    e = zone_edges(T)
    for z in range(6):
        s = np.linspace(e[z], e[z + 1], 30)
        pts = _oval_px(s, np.full_like(s, 5.0), scale, cx, cy).astype(np.int32)
        a = 0.18 + 0.82 * float(probs[z])
        col = tuple(int(c * a) for c in COLS[z])
        cv2.polylines(p, [pts], False, col, 11 if z + 1 == reported else 7, cv2.LINE_AA)
        m = _oval_px((e[z] + e[z + 1]) / 2, 17.0, scale, cx, cy).astype(int)
        cv2.putText(p, str(z + 1), (m[0] - 5, m[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLS[z], 1, cv2.LINE_AA)
    # meta y salida del 1500
    for s0, col in ((0.0, (255, 255, 255)), (start_s(1500), (0, 215, 255))):
        a_, b_ = _oval_px(s0, np.array([-1.0, 11.0]), scale, cx, cy).astype(int)
        cv2.line(p, tuple(a_), tuple(b_), col, 2, cv2.LINE_AA)
    # incertidumbre (arco) y posición estimada
    s_m, sd = est["s"], max(est["x_std"], 1.0)
    arc = np.linspace(s_m - sd, s_m + sd, 20)
    cv2.polylines(p, [_oval_px(arc, np.full_like(arc, 13.0), scale, cx, cy).astype(np.int32)], False, (0, 255, 255), 3, cv2.LINE_AA)
    q = _oval_px(s_m, 5.0, scale, cx, cy).astype(int)
    cv2.circle(p, tuple(q), 6, (0, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(p, tuple(q), 6, (0, 0, 0), 1, cv2.LINE_AA)
    if truth is not None and truth.get("s_lider") is not None:
        tq = _oval_px(truth["s_lider"], -3.0, scale, cx, cy).astype(int)
        cv2.drawMarker(p, tuple(tq), (255, 255, 255), cv2.MARKER_TRIANGLE_UP, 9, 1, cv2.LINE_AA)

    # ---- texto principal
    x0 = 245
    cv2.putText(p, f"Z{reported}", (x0, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.3, COLS[reported - 1], 3, cv2.LINE_AA)
    cv2.putText(p, f"{probs[reported - 1]:.0%}", (x0 + 72, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
    name = NAMES[reported]
    lines = [name[:name.rfind(" ")], name[name.rfind(" ") + 1:]] if name.startswith("curva") else name.split(" ", 1)
    for k, line in enumerate(lines):
        cv2.putText(p, line, (x0, 92 + 18 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1, cv2.LINE_AA)
    x = min(max(est["x"], 0.0), 1500.0)
    cv2.putText(p, f"{x:.0f} m  (+/-{est['x_std']:.0f})", (x0, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(p, f"faltan {1500 - x:.0f} m", (x0, 158), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(p, f"t carrera {max(info['t'], 0):.1f} s", (x0, 176), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    # ---- barras
    by, bw = 245, 52
    for z in range(6):
        h = int(40 * probs[z])
        bx = 14 + z * 60
        cv2.rectangle(p, (bx, by - 40), (bx + bw, by), (55, 55, 55), -1)
        cv2.rectangle(p, (bx, by - h), (bx + bw, by), COLS[z], -1)
        cv2.putText(p, f"Z{z + 1}", (bx + 14, by + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)

    # ---- avisos
    chips = []
    if info["cut_age"] < 0.8:
        chips.append(("CORTE", (0, 0, 220)))
    if info["recognized"]:
        chips.append(("camara reconocida", (40, 150, 40)))
    if info["curv"] is not None:
        chips.append((("lineas curvas" if info["curv"] > 0.5 else "lineas rectas"), (120, 90, 40)))
    cxp = 12
    for txt, col in chips:
        (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        cv2.rectangle(p, (cxp, 272), (cxp + tw + 10, 292), col, -1)
        cv2.putText(p, txt, (cxp + 5, 287), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        cxp += tw + 16
    if truth is not None:
        cv2.drawMarker(p, (PW - 128, 283), (255, 255, 255), cv2.MARKER_TRIANGLE_UP, 9, 1, cv2.LINE_AA)
        cv2.putText(p, "cabeza (borrador)", (PW - 120, 287), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1, cv2.LINE_AA)
    if truth is not None and truth.get("zone"):
        ok = truth["zone"] == reported
        cv2.putText(p, f"borrador: Z{truth['zone']}", (PW - 118, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (120, 220, 120) if ok else (90, 90, 255), 1, cv2.LINE_AA)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/ncaa1500.mp4")
    ap.add_argument("--out", default="out/zonas.mp4")
    ap.add_argument("--t0", type=float, default=58.7, help="segundo del video del disparo")
    ap.add_argument("--from", dest="t_from", type=float, default=-3.0, help="desde (s de carrera)")
    ap.add_argument("--to", dest="t_to", type=float, default=232.0, help="hasta (s de carrera)")
    ap.add_argument("--labels", default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    truth = {}
    if a.labels:
        truth = {r["t_race"]: r for r in map(json.loads, open(a.labels))}

    cap = cv2.VideoCapture(a.source)
    fps = cap.get(cv2.CAP_PROP_FPS)
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    i = int(round((a.t0 + a.t_from) * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"avc1"), fps / 2, (W, H))
    if not out.isOpened():
        out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), fps / 2, (W, H))

    zf, rep, mem, sd = ZoneFilter(1500, seed=a.seed), ZoneReporter(), CameraMemory(), ShotDetector()
    next_sample, last_cut, cut_pending = 0.0, -99.0, False
    reported, recognized, curv_p = None, False, None
    tic = time.time()
    n = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        t = i / fps - a.t0
        i += 1
        if t > a.t_to:
            break
        if (i - 1) % 2:   # 30 fps duplicado a 60: se procesa y escribe uno de cada dos
            continue
        if sd(f, t):
            cut_pending, last_cut = True, t
        zf.predict(t)
        if t >= next_sample - 0.5 / fps and t >= 0:
            if cut_pending:
                zf.on_cut()
                cut_pending = False
            c = line_curvature(f)
            lik_c = curvature_likelihood(c)
            curv_p = None
            if lik_c is not None:
                zf.update(lik_c)
                # para el aviso: ¿la evidencia favorece curva o recta?
                curv_p = float(lik_c(np.array([30.0]))[0] > lik_c(np.array([150.0]))[0]) if c["chord"] > 300 else None
            desc = descriptor(f)
            lik_m = mem.likelihood(desc, t)
            recognized = lik_m is not None
            if recognized:
                zf.update(lik_m)
            est = zf.estimate()
            reported = rep(np.array(est["p"]))
            mem.add(desc, est["s"], est["x_std"], t)
            next_sample += 0.5
        est = zf.estimate()
        if reported is None:
            reported = est["zone"]
        tr = truth.get(round(round(t * 2) / 2, 3)) if truth and t >= 0 else None
        panel = draw_panel(est, np.array(est["p"]), reported,
                           {"t": t, "cut_age": t - last_cut, "recognized": recognized, "curv": curv_p}, tr)
        x0, y0 = W - PW - 16, 70
        roi = f[y0:y0 + PH, x0:x0 + PW]
        f[y0:y0 + PH, x0:x0 + PW] = cv2.addWeighted(roi, 0.3, panel, 0.7, 0)
        cv2.rectangle(f, (x0, y0), (x0 + PW, y0 + PH), (80, 80, 80), 1)
        out.write(f)
        n += 1
    out.release()
    print(f"{n} frames -> {a.out} ({time.time() - tic:.0f} s)")


if __name__ == "__main__":
    main()
