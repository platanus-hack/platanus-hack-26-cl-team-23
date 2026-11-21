"""Cuadro de muestra del tema "Pista" sobre un video real con su seguimiento.

Uso:
  python -m app.cv.demo_theme --video NCCA.mp4 --tracks NCCA.tracks.json --frame 400 --chosen 1 \
      --out out/despues.png

Dibuja: esquinas + píldora por corredor (el elegido en naranja), estelas de los pies,
y un panel de vidrio con la zona enfocada y el óvalo cenital. Los datos de zona
(--zone, --s, --sd) son de ejemplo: en el render real salen del filtro de zonas.
"""

import argparse
import json

import cv2

from app.cv import theme as th

# mismas zonas que trazada.zones.NAMES, en oración normal
ZONES = {
    1: "Curva 1, entrada",
    2: "Curva 1, salida",
    3: "Recta opuesta",
    4: "Curva 2, entrada",
    5: "Curva 2, salida",
    6: "Recta principal",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--tracks", required=True)
    ap.add_argument("--frame", type=int, default=400, help="cuadro del video original")
    ap.add_argument("--chosen", type=int, default=1, help="id del corredor elegido")
    ap.add_argument("--trail", type=int, default=12, help="cuadros de seguimiento en la estela")
    ap.add_argument("--zone", type=int, default=3)
    ap.add_argument("--s", type=float, default=150.0, help="s estimado del foco (m desde la meta)")
    ap.add_argument("--sd", type=float, default=9.0)
    ap.add_argument("--meters", type=float, default=312.0, help="metros recorridos (ejemplo)")
    ap.add_argument("--out", default="out/despues.png")
    a = ap.parse_args()

    with open(a.tracks) as fh:
        data = json.load(fh)
    frames = {f["frame"]: f for f in data["frames"]}
    keys = sorted(k for k in frames if k <= a.frame)
    cur = frames[keys[-1]]
    hist = [frames[k] for k in keys[-a.trail :]]

    cap = cv2.VideoCapture(a.video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, cur["frame"])
    ok, img = cap.read()
    assert ok, "no se pudo leer el cuadro"
    sc = th.Scale(img.shape[0])

    # estelas con suavizado causal (solo pasado), primero para que queden debajo
    sm = th.Smoother(tau=0.25)
    trails = {}
    for f in hist:
        for p in f["detections"]:
            trails.setdefault(p["id"], []).append(sm(p["id"], p["foot_px"], f["t"]))
    for d in cur["detections"]:
        th.trail(img, trails.get(d["id"], []), sc, chosen=d["id"] == a.chosen)
    # cajas y etiquetas: el elegido al final para que quede encima
    for d in sorted(cur["detections"], key=lambda d: d["id"] == a.chosen):
        ch = d["id"] == a.chosen
        th.corners(img, d["bbox"], sc, chosen=ch)
        x1, y1 = d["bbox"][0], d["bbox"][1]
        if ch:
            th.pill(img, (x1, y1 - sc.px(10)), f"#{d['id']}", sc, chosen=True, anchor="lb")
        else:
            th.pill(
                img, (x1, y1 - sc.px(8)), f"{d['id']}", sc, role="label", anchor="lb", alpha=0.9
            )

    # panel de vidrio: abajo a la derecha, pero dentro de la zona segura (sobre el reloj de carrera)
    sx, sy, sw, shh = th.safe_rect(img)
    pw, ph = sc.px(660), sc.px(300)
    px, py = sx + sw - pw, sy + shh - ph
    th.glass_panel(img, (px, py, pw, ph), sc)
    m = sc.px(28)
    th.text(img, (px + m, py + m), "Zona enfocada", sc, role="label", color="ink_soft")
    th.text(img, (px + m, py + m + sc.px(44)), ZONES[a.zone], sc, role="title")
    th.text(
        img,
        (px + m, py + m + sc.px(108)),
        th.fmt_num(a.meters, 0, "m"),
        sc,
        role="figure",
        tabular=True,
    )
    th.text(
        img,
        (px + m, py + ph - m),
        f"± {th.fmt_num(a.sd, 0, 'm')} · faltan {th.fmt_num(1500 - a.meters, 0, 'm')}",
        sc,
        role="text",
        color="ink_soft",
        anchor="lb",
        tabular=True,
    )
    ow = sc.px(310)
    th.oval(
        img,
        (px + pw - ow - sc.px(8), py + sc.px(20), ow, ph - sc.px(90)),
        sc,
        zone=a.zone,
        s_est=a.s,
        s_sd=a.sd,
        glass=False,
    )

    cv2.imwrite(a.out, img)
    print("->", a.out)


if __name__ == "__main__":
    main()
