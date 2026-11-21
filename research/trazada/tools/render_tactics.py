#!/usr/bin/env python
"""Video con el pronóstico del final y las recomendaciones de adelantamiento, en vivo (causal).

Toma el video ya anotado de render_athletes (un frame por línea de atletas.jsonl) y le agrega
un panel a la derecha, con los mismos colores por atleta que las cajas:
  - tiempo ganador pronosticado (p50 y banda p10–p90 en el tiempo; la línea "real" es solo
    referencia, el pronóstico no la usa)
  - tabla: P(gana), P(podio), llegada estimada
  - adelantamientos: las 3 mejores oportunidades, con un mapa de lo que falta (curvas/rectas),
    la ventana de ataque y el punto ideal

  python -m tools.render_tactics [--video out/atletas_raw.mp4] [--atletas out/atletas.jsonl] \
      [--out out/tacticas_raw.mp4] [--from 0 --to 230]
  avconvert -p Preset1920x1080 -s out/tacticas_raw.mp4 -o out/tacticas.mp4   # comprimir (macOS)
"""
import argparse
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tools.render_athletes import ath_color
from trazada.forecast import FinishForecaster, ForecastConfig
from trazada.geometry import STANDARD as T
from trazada.overtake import OvertakeAdvisor
from trazada.zones import start_s

SW = 400                       # ancho del panel
DIST = 1500
BG, FG, DIM, ACC = (18, 20, 24), (235, 235, 235), (140, 145, 155), (255, 196, 61)
GOOD, BAD = (90, 200, 120), (230, 90, 80)
CURVE, STRAIGHT = (150, 92, 70), (58, 62, 70)     # tartán (curva) vs gris (recta)


def _font(size, bold=False):
    for path, idx in (("/System/Library/Fonts/HelveticaNeue.ttc", 1 if bold else 0),
                      ("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0)):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


F_H, F_B, F_S, F_XS = _font(19, True), _font(15), _font(13), _font(11)


def rgb(i):
    b, g, r = ath_color(i)
    return r, g, b


def mmss(s):
    return f"{int(s // 60)}:{s % 60:05.2f}"


def is_curve(togo):
    s = (start_s(DIST) + DIST - togo) % T.lap
    return T.segment(s).startswith("curva")


def draw_history(d: ImageDraw.ImageDraw, y, hist, truth, t_now):
    x0, x1, h = 16, SW - 16, 70
    t_max, lo, hi = 230.0, 215.0, 250.0
    X = lambda t: x0 + (x1 - x0) * min(t, t_max) / t_max
    Y = lambda v: y + h - (h * (min(max(v, lo), hi) - lo) / (hi - lo))
    d.rectangle([x0, y, x1, y + h], outline=(50, 54, 60))
    for v in (220, 230, 240):
        d.line([x0, Y(v), x1, Y(v)], fill=(38, 41, 46))
        d.text((x1 - 26, Y(v) - 13), mmss(v)[:4], font=F_XS, fill=DIM)
    if truth:
        for xx in range(x0, x1, 8):
            d.line([xx, Y(truth), xx + 4, Y(truth)], fill=(110, 110, 110))
        d.text((x0 + 4, Y(truth) - 14), f"real {mmss(truth)} (referencia)", font=F_XS, fill=DIM)
    if len(hist) > 1:
        top = [(X(t), Y(p90)) for t, _, _, p90 in hist]
        bot = [(X(t), Y(p10)) for t, p10, _, _ in hist][::-1]
        d.polygon(top + bot, fill=(70, 60, 30))
        d.line([(X(t), Y(p50)) for t, _, p50, _ in hist], fill=ACC, width=2)
    d.line([X(t_now), y, X(t_now), y + h], fill=(80, 84, 90))
    return y + h


def draw_duel_map(d, y, rec, r_now):
    """Barra de lo que falta (izq = ahora, der = meta): curvas oscuras, ventana, ideal."""
    x0, x1, h = 16, SW - 16, 10
    span = max(r_now, 1.0)
    X = lambda togo: x0 + (x1 - x0) * (1 - togo / span)
    # bloques contiguos de curva/recta (sin rayado por aliasing)
    marks = np.arange(span, -1e-9, -1.0)
    kinds = [is_curve(m) for m in marks]
    k0 = 0
    for k in range(1, len(marks) + 1):
        if k == len(marks) or kinds[k] != kinds[k0]:
            end = marks[k] if k < len(marks) else 0.0
            d.rectangle([X(marks[k0]), y, max(X(end), X(marks[k0])), y + h],
                        fill=CURVE if kinds[k0] else STRAIGHT)
            k0 = k
    w0, w1 = (float(np.clip(w, 0, span)) for w in rec["window"])
    xa, xb = sorted((X(w0), X(w1)))
    d.rectangle([xa, y - 2, xb, y + h + 2], outline=GOOD, width=2)
    xi = X(min(rec["at_m"], span))
    d.polygon([(xi - 5, y - 7), (xi + 5, y - 7), (xi, y)], fill=ACC)
    now = rec["at_m"] >= span - 1
    if not now:
        d.text((x0, y + h + 2), "ahora", font=F_XS, fill=DIM)
    d.text((x1 - 30, y + h + 2), "meta", font=F_XS, fill=DIM)
    d.text((max(xi - 14, x0), y + h + 2), "ya" if now else f"{rec['at_m']:.0f} m", font=F_XS, fill=ACC)
    return y + h + 16


def render_panel(H, t, fc, recs, hist, truth, lead_x):
    im = Image.new("RGB", (SW, H), BG)
    d = ImageDraw.Draw(im)
    togo = DIST - lead_x
    d.text((16, 12), "PRONÓSTICO DEL FINAL", font=F_H, fill=FG)
    d.text((16, 36), f"t {mmss(max(t, 0))}   ·   a la cabeza le faltan {max(togo, 0):.0f} m", font=F_S, fill=DIM)
    y = 60
    if fc and fc["winner"]:
        p10, p50, p90 = fc["winner"]
        d.text((16, y), "Tiempo ganador", font=F_S, fill=DIM)
        d.text((16, y + 16), mmss(p50), font=_font(28, True), fill=ACC)
        d.text((150, y + 28), f"80 %: {mmss(p10)} – {mmss(p90)}", font=F_S, fill=FG)
    y = draw_history(d, y + 56, hist, truth, t) + 12

    # tabla
    d.text((16, y), "atleta", font=F_XS, fill=DIM)
    d.text((80, y), "P(gana)", font=F_XS, fill=DIM)
    d.text((215, y), "P(podio)", font=F_XS, fill=DIM)
    d.text((300, y), "llegada", font=F_XS, fill=DIM)
    y += 16
    for a in (fc["athletes"][:7] if fc else []):
        c = rgb(a["id"])
        d.ellipse([16, y + 3, 26, y + 13], fill=c)
        d.text((32, y), f"#{a['id']}", font=F_B, fill=c)
        d.rectangle([80, y + 4, 80 + 120, y + 14], fill=(40, 43, 48))
        d.rectangle([80, y + 4, 80 + 120 * a["p_win"], y + 14], fill=c)
        d.text((80 + 124, y), f"{a['p_win']:.0%}", font=F_XS, fill=FG)
        d.text((240, y), f"{a['p_podium']:.0%}", font=F_S, fill=FG)
        d.text((300, y), mmss(a["eta"][1]), font=F_S, fill=FG)
        y += 21
    y += 8
    d.line([16, y, SW - 16, y], fill=(50, 54, 60))
    y += 8

    d.text((16, y), "¿CUÁNDO ADELANTAR?", font=F_H, fill=FG)
    lx = SW - 150
    d.rectangle([lx, y + 6, lx + 10, y + 14], fill=CURVE)
    d.text((lx + 14, y + 3), "curva", font=F_XS, fill=DIM)
    d.rectangle([lx + 60, y + 6, lx + 70, y + 14], fill=STRAIGHT)
    d.text((lx + 74, y + 3), "recta", font=F_XS, fill=DIM)
    y += 28
    if not recs:
        d.text((16, y), "sin duelos a menos de 15 m", font=F_S, fill=DIM)
    for r in recs:
        if y > H - 70:
            break
        ca, cb = rgb(r["id"]), rgb(r["rival"])
        d.text((16, y), f"#{r['id']}", font=F_B, fill=ca)
        d.line([52, y + 10, 70, y + 10], fill=DIM, width=2)
        d.polygon([(70, y + 5), (70, y + 15), (76, y + 10)], fill=DIM)
        d.text((82, y), f"#{r['rival']}", font=F_B, fill=cb)
        d.text((126, y + 2), f"a {r['gap']:.1f} m", font=F_S, fill=DIM)
        pc = GOOD if r["p_attack"] >= 0.5 else (ACC if r["p_attack"] >= 0.35 else BAD)
        d.text((SW - 70, y), f"{r['p_attack']:.0%}", font=F_B, fill=pc)
        y += 20
        act = r["action"]
        col = GOOD if act.startswith("ATACAR") else (ACC if act.startswith("ESPERAR") else DIM)
        d.text((16, y), act, font=F_S, fill=col)
        y += 18
        d.text((16, y), r["why"][:62], font=F_XS, fill=DIM)
        y += 20
        y = draw_duel_map(d, y, r, r["r_now"]) + 10
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="out/atletas_raw.mp4")
    ap.add_argument("--atletas", default="out/atletas.jsonl")
    ap.add_argument("--out", default="out/tacticas_raw.mp4")
    ap.add_argument("--truth", type=float, default=227.27, help="solo se dibuja como referencia")
    ap.add_argument("--from", dest="t_from", type=float, default=-2.0)
    ap.add_argument("--to", dest="t_to", type=float, default=1e9)
    ap.add_argument("--fc_every", type=float, default=0.5)
    ap.add_argument("--ot_every", type=float, default=1.0)
    ap.add_argument("--snap", type=float, nargs="*", default=[], help="guardar PNG en estos t")
    a = ap.parse_args()

    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    W, H = int(cap.get(3)), int(cap.get(4))
    out = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"avc1"), fps, (W + SW, H))
    fcst = FinishForecaster(ForecastConfig(distance=DIST), seed=0)
    adv = OvertakeAdvisor(seed=0)
    hist, fc, recs, panel = [], None, [], None
    t_fc = t_ot = -1e9
    snaps = sorted(a.snap)
    n = 0
    for line in open(a.atletas):
        ok, frame = cap.read()
        if not ok:
            break
        fr = json.loads(line)
        t, A = fr["t"], fr["athletes"]
        if t >= 0 and A:
            fcst.observe(t, A)
            adv.observe(t, A)
        dirty = panel is None
        if t >= 0 and A and t - t_fc >= a.fc_every:
            t_fc, dirty = t, True
            fc = fcst.forecast(t, ids=[x["id"] for x in A])
            hist.append((t, *fc["winner"]))
        if t >= 0 and A and t - t_ot >= a.ot_every:
            t_ot, dirty = t, True
            recs = []
            for x in A:
                r = adv.recommend(x["id"], t)
                if r["rival"] is not None:
                    r["r_now"] = DIST - adv.ath[r["rival"]].x
                    if r["r_now"] >= 10:              # a menos de 10 m ya no hay decisión
                        recs.append(r)
            recs.sort(key=lambda r: -r["p_attack"])
            recs = recs[:3]
        if t < a.t_from or t > a.t_to:
            continue
        if dirty:
            lead_x = max((x["x"] for x in A), default=fr["group"]["x"])
            panel = render_panel(H, t, fc, recs, hist, a.truth, lead_x)
        img = np.hstack([frame, panel])
        out.write(img)
        n += 1
        while snaps and t >= snaps[0]:
            p = a.out.replace(".mp4", f"_{snaps.pop(0):.0f}.jpg")
            cv2.imwrite(p, img)
            print("->", p)
    out.release()
    print(f"{n} frames -> {a.out}")


if __name__ == "__main__":
    main()
