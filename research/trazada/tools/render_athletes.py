#!/usr/bin/env python
"""Video de la carrera con la posición y velocidad de cada atleta respecto a la cancha.

Uso:
  python -m tools.render_athletes --out out/atletas_raw.mp4 [--from 0 --to 230] [--jsonl out/atletas.jsonl]
  avconvert -p Preset1280x720 -s out/atletas_raw.mp4 -o out/atletas.mp4      # comprimir (macOS)

Todo causal, frame a frame (como en vivo):
  1. Grupo: filtro de zonas (reloj + salida reglamentaria + cortes + memoria de cámaras +
     curvatura) -> metros recorridos por la cabeza (x_grupo) y su velocidad (v_grupo).
  2. Atletas: YOLO26 + BoT-SORT; filtro de corredores (pies sobre tartán, tamaño del grupo).
  3. Dentro del frame: Δs de cada uno respecto al grupo (escala = alto del cuerpo, dirección =
     líneas de pista) y d al bordillo (contando calles). "Adelante" sale del movimiento de los
     corredores respecto al fondo.
  4. Kalman por atleta: x = x_grupo + Δs, v = v_grupo + u; re-identificación tras cortes por
     posición predicha + color de camiseta.
Dibuja: etiqueta por atleta (puesto, metros recorridos, calle, velocidad), los atletas en el óvalo
y una vista cenital del grupo (metros detrás de la cabeza × distancia al bordillo).
"""
import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from tools.render_zones import COLS, PH, PW, _oval_px, draw_panel
from trazada.athletes import AthleteTracker, IGNORE_TV, LANE, measure_frame, select_runners
from trazada.evidence import CameraMemory, curvature_likelihood, descriptor, line_curvature
from trazada.geometry import STANDARD as T
from trazada.ground_speed import GroundSpeedGate
from trazada.pipeline import TRACKER_DIR, _best_device
from trazada.shots import ShotDetector
from trazada.zone_filter import ZoneFilter, ZoneReporter

GW, GH = 400, 170          # panel del grupo
BEHIND = 30.0              # metros detrás de la cabeza que muestra el panel


def ath_color(i):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.65, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


def lane_of(d):
    return int(min(9, max(0, d) // LANE + 1))


def draw_group(athletes, x_lead, v_group, t):
    """Vista cenital del grupo: eje x = metros respecto a la cabeza (0 a la derecha),
    eje y = distancia al bordillo (pasto abajo)."""
    p = np.zeros((GH, GW, 3), np.uint8)
    p[:] = (25, 25, 25)
    x0, x1, y0, y1 = 18, GW - 14, 36, GH - 22
    dmax = 4 * LANE
    X = lambda dx: int(x0 + (dx + BEHIND) / (BEHIND + 2) * (x1 - x0))
    Y = lambda d: int(y1 - min(d, dmax) / dmax * (y1 - y0))
    cv2.rectangle(p, (x0, y0), (x1, y1), (40, 45, 120), -1)
    cv2.rectangle(p, (x0, y1), (x1, y1 + 6), (60, 120, 60), -1)           # pasto (adentro)
    for k in range(1, 4):
        cv2.line(p, (x0, Y(k * LANE)), (x1, Y(k * LANE)), (200, 200, 200), 1)
    for m in range(-30, 1, 5):
        cv2.line(p, (X(m), y1 + 6), (X(m), y1 + 10), (150, 150, 150), 1)
        cv2.putText(p, f"{m}", (X(m) - 8, GH - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(p, f"GRUPO  v {v_group:.1f} m/s   cabeza {x_lead:.0f} m", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255), 1, cv2.LINE_AA)
    for a in athletes:
        dx = a.x - x_lead
        if dx < -BEHIND - 1:
            continue
        age = t - a.last_t
        col = ath_color(a.id) if age < 0.5 else (110, 110, 110)
        c = (X(dx), Y(a.d))
        cv2.circle(p, c, 7, col, -1, cv2.LINE_AA)
        cv2.putText(p, str(a.id), (c[0] - 5, c[1] - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.36, col, 1, cv2.LINE_AA)
    return p


def stable_order(athletes, prev_ids, margin=0.4):
    """Orden por metros recorridos con histéresis: dos atletas solo cambian de puesto si la
    diferencia supera `margin` (en un grupo apretado, el ruido de ±0,5 m invertiría el orden
    a cada frame)."""
    pos = {i: k for k, i in enumerate(prev_ids)}
    order = sorted(athletes, key=lambda q: (pos.get(q.id, len(pos)), -q.x))
    changed = True
    while changed:
        changed = False
        for k in range(len(order) - 1):
            a, b = order[k], order[k + 1]
            new_b = b.id not in pos
            if b.x > a.x + (0.0 if new_b else margin):
                order[k], order[k + 1] = b, a
                changed = True
    return order


def label(img, a, rank, v_group):
    x1, y1, x2, y2 = (int(v) for v in a.box)
    col = ath_color(a.id)
    cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
    s = a.x % T.lap
    l1 = f"{rank}. #{a.id}"
    l2 = f"{a.x:.0f}m c{lane_of(a.d)} {v_group + a.u:.1f}m/s"
    for k, txt in enumerate((l1, l2)):
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        y = y1 - 6 - (1 - k) * 16
        cv2.rectangle(img, (x1, y - th - 3), (x1 + tw + 4, y + 3), (20, 20, 20), -1)
        cv2.putText(img, txt, (x1 + 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, col if k == 0 else (255, 255, 255), 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/ncaa1500.mp4")
    ap.add_argument("--out", default="out/atletas_raw.mp4")
    ap.add_argument("--jsonl", default="out/atletas.jsonl")
    ap.add_argument("--t0", type=float, default=58.7, help="segundo del video del disparo")
    ap.add_argument("--from", dest="t_from", type=float, default=-2.0)
    ap.add_argument("--to", dest="t_to", type=float, default=230.0)
    ap.add_argument("--model", default="yolo26s.pt")
    ap.add_argument("--tracker", default="botsort_broadcast.yaml")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--field", type=int, default=12, help="corredores en la serie")
    ap.add_argument("--ground", default="out/ground_speed.jsonl",
                    help="velocidad contra el suelo (tools.ground_speed_features); '' para no usarla")
    a = ap.parse_args()
    ground = [json.loads(l) for l in open(a.ground)] if a.ground and Path(a.ground).exists() else []
    gate, gi = GroundSpeedGate(cos_min=0.9, sigma=0.8), 0

    from ultralytics import YOLO
    model = YOLO(a.model)
    device = _best_device()
    trk_cfg = str(TRACKER_DIR / a.tracker)

    cap = cv2.VideoCapture(a.source)
    fps = cap.get(cv2.CAP_PROP_FPS)
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    i = int(round((a.t0 + a.t_from) * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"avc1"), fps / 2, (W, H))
    jl = open(a.jsonl, "w") if a.jsonl else None

    zf, rep, mem, sd = ZoneFilter(1500), ZoneReporter(), CameraMemory(), ShotDetector()
    ath = AthleteTracker(field_size=a.field)
    next_sample, last_cut, cut_pending, cut_for_ath = 0.0, -99.0, False, False
    reported, recognized, curv_p = None, False, None
    prev_gray, prev_feet, fwd = None, {}, None
    prev_order = []
    tic, n, t_proc = time.time(), 0, []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        t = i / fps - a.t0
        i += 1
        if t > a.t_to:
            break
        if (i - 1) % 2:   # 30 fps duplicado a 60
            continue
        t_a = time.perf_counter()
        is_cut = sd(f, t)
        if is_cut:
            cut_pending, cut_for_ath, last_cut = True, True, t
            prev_feet, fwd = {}, None
        # ---- grupo (filtro de zonas)
        while gi < len(ground) and ground[gi]["t"] <= t:      # velocidad contra el suelo, causal
            g = ground[gi]
            gate.add(g["t"], g["v"], g["cos"])
            if g["t"] >= 0 and (m := gate.measure(g["t"])):
                zf.predict(g["t"])
                zf.update_v(*m)
            gi += 1
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
        x_group, v_group = (max(est["x"], 0.0), est["v"]) if t >= 0 else (0.0, 0.0)

        # ---- atletas
        res = model.track(f, persist=True, tracker=trk_cfg, classes=[0], imgsz=a.imgsz, conf=0.3,
                          device=device, verbose=False)[0]
        bx = res.boxes
        boxes = bx.xyxy.cpu().numpy() if bx is not None and len(bx) else np.zeros((0, 4))
        tids = bx.id.int().cpu().numpy() if bx is not None and bx.id is not None else np.full(len(boxes), -1)
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        runners = select_runners(boxes, hsv)
        # "adelante": movimiento de los corredores respecto al fondo (la cámara panea con ellos)
        gray = cv2.cvtColor(cv2.resize(f[60:640], (320, 145)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        feet_now = {int(tids[k]): np.array([(boxes[k, 0] + boxes[k, 2]) / 2, boxes[k, 3]]) for k in runners}
        if prev_gray is not None and not is_cut and feet_now:
            (sx, sy), _ = cv2.phaseCorrelate(prev_gray, gray)
            bg = np.array([sx * W / 320, sy * 580 / 145])
            rel = [feet_now[k] - prev_feet[k] - bg for k in feet_now if k in prev_feet]
            if rel:
                mv = np.median(rel, 0)
                if np.linalg.norm(mv) > 0.5:
                    mv = mv / np.linalg.norm(mv)
                    fwd = mv if fwd is None else 0.8 * fwd + 0.2 * mv
        prev_gray, prev_feet = gray, feet_now
        geo, meas = measure_frame(f, boxes, runners, fwd_hint=fwd)
        ath.predict(t, v_group)
        live = []
        # sin sentido "adelante" conocido (recién empezado un plano lateral) Δs tiene signo al azar:
        # solo se actualiza lo lateral y la asignación
        if geo is not None and not geo.head_on and fwd is None:
            for m in meas:
                m["sigma_ds"] = 1e3
        if t >= 0 and geo is not None and meas:
            m_t = [int(tids[m["idx"]]) if tids[m["idx"]] >= 0 else None for m in meas]
            live = ath.update(t, x_group, meas, m_t, boxes, f, cut=cut_for_ath)
            cut_for_ath = False
        t_proc.append(time.perf_counter() - t_a)

        # ---- dibujo
        order = stable_order([q for q in ath.ath.values() if t - q.last_t < 3.0], prev_order)
        prev_order = [q.id for q in order]
        rank = {q.id: k + 1 for k, q in enumerate(order)}
        for q in live:
            label(f, q, rank[q.id], v_group)
        panel = draw_panel(est, np.array(est["p"]), reported,
                           {"t": t, "cut_age": t - last_cut, "recognized": recognized, "curv": curv_p}, None)
        cx, cy, scale = 120, 125, 210 / (T.straight + 2 * (T.radius + 12))
        for q in order:
            if t - q.last_t > 3:
                continue
            pt = _oval_px(q.x % T.lap, 2.0 + q.d, scale, cx, cy).astype(int)
            cv2.circle(panel, tuple(pt), 3, ath_color(q.id), -1, cv2.LINE_AA)
        x0, y0 = W - PW - 16, 70
        f[y0:y0 + PH, x0:x0 + PW] = cv2.addWeighted(f[y0:y0 + PH, x0:x0 + PW], 0.3, panel, 0.7, 0)
        gp = draw_group(order, order[0].x if order else x_group, v_group, t)
        gx, gy = 16, 72
        f[gy:gy + GH, gx:gx + GW] = cv2.addWeighted(f[gy:gy + GH, gx:gx + GW], 0.3, gp, 0.7, 0)
        out.write(f)
        if jl is not None:
            jl.write(json.dumps({
                "t": round(t, 3), "zone": reported, "group": {"x": round(x_group, 1), "v": round(v_group, 2)},
                "view": None if geo is None else {"head_on": geo.head_on, "k": round(geo.k, 2),
                                                  "phi_deg": round(math.degrees(geo.phi), 1)},
                "athletes": [{"id": q.id, "rank": rank[q.id], "x": round(q.x, 1), "s": round(q.x % T.lap, 1),
                              "d": round(q.d, 2), "lane": lane_of(q.d), "v": round(v_group + q.u, 2),
                              "u": round(q.u, 2), "visible": t - q.last_t < 0.05,
                              "sigma_x": round(math.sqrt(q.P[0, 0]), 2)} for q in order]}) + "\n")
        n += 1
    out.release()
    if jl is not None:
        jl.close()
    print(f"{n} frames -> {a.out}  ({time.time() - tic:.0f} s, {1000 * np.mean(t_proc):.0f} ms/frame de cómputo)")


if __name__ == "__main__":
    main()
