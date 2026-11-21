#!/usr/bin/env python
"""Evalúa el filtro de zonas contra las etiquetas de label_zones.py.

Uso:
  python -m tools.eval_zones data/zones_labels.jsonl [--features out/zone_feats.npz]
         [--cuts none|oracle|detected] [--evidence none|mem|curv|mem+curv] [--ablation]

El prior es la salida reglamentaria + ritmo plausible + reloj de carrera. Con `--features`
(de tools.zone_features) se agrega evidencia visual: memoria de cámaras y curvatura de líneas.
`--cuts oracle` usa los cortes etiquetados; `detected`, los del detector causal.
Reporta exactitud en las muestras con zona conocida, exactitud por tipo de plano y después de un corte, cambios de zona falsos y la matriz de confusión.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from trazada.evidence import CameraMemory, curvature_likelihood
from trazada.zone_filter import ZoneFilter, ZoneReporter


def load_features(path):
    F = np.load(path)
    return {round(float(t), 3): {"cut": bool(c), "desc": d, "bend": float(b), "chord": float(ch), "n": int(n)}
            for t, c, d, b, ch, n in zip(F["t"], F["cut"], F["desc"], F["bend"], F["chord"], F["n"])}


def run(labels, cuts="none", distance=1500, seed=0, feats=None, evidence="none"):
    """Recorre las muestras en orden temporal, usando solo el presente y el pasado."""
    zf, rep, mem = ZoneFilter(distance, seed=seed), ZoneReporter(), CameraMemory()
    use_mem, use_curv = "mem" in evidence, "curv" in evidence
    preds = []
    for r in labels:
        f = feats.get(round(r["t_race"], 3)) if feats else None
        zf.predict(r["t_race"])
        if (cuts == "oracle" and r.get("cut")) or (cuts == "detected" and f and f["cut"]):
            zf.on_cut()
        recog = False
        if f is not None:
            if use_curv and (lik := curvature_likelihood(f)) is not None:
                zf.update(lik)
            if use_mem and (lik := mem.likelihood(f["desc"], r["t_race"])) is not None:
                zf.update(lik)
                recog = True
        est = zf.estimate()
        est["reported"] = rep(np.array(est["p"]))
        est["recognized"] = recog
        if f is not None and use_mem:
            est["remembered"] = mem.add(f["desc"], est["s"], est["x_std"], r["t_race"])
        preds.append(est)
    return preds


def report(labels, preds):
    ok = [(r, p) for r, p in zip(labels, preds) if r.get("zone")]
    if not ok:
        print("sin etiquetas con zona")
        return
    acc = np.mean([p["reported"] == r["zone"] for r, p in ok])
    acc_map = np.mean([p["zone"] == r["zone"] for r, p in ok])
    print(f"muestras con zona: {len(ok)}/{len(labels)}")
    print(f"exactitud (con histéresis): {acc:.1%}   (argmax directo: {acc_map:.1%})")
    for shot in sorted({r.get("shot") for r, _ in ok}):
        sub = [(r, p) for r, p in ok if r.get("shot") == shot]
        print(f"  plano {shot:<13} n={len(sub):>4}  exactitud {np.mean([p['reported'] == r['zone'] for r, p in sub]):.1%}")
    # después de un corte (2 s siguientes)
    cut_t, after = [r["t_race"] for r in labels if r.get("cut")], []
    for r, p in ok:
        if any(0 <= r["t_race"] - c <= 2.0 for c in cut_t):
            after.append(p["reported"] == r["zone"])
    if after:
        print(f"  2 s tras un corte   n={len(after):>4}  exactitud {np.mean(after):.1%}")
    # cambios de zona reportados que no existen en la verdad
    rz = [p["reported"] for _, p in ok]
    gz = [r["zone"] for r, _ in ok]
    sw_pred = sum(a != b for a, b in zip(rz, rz[1:]))
    sw_true = sum(a != b for a, b in zip(gz, gz[1:]))
    print(f"cambios de zona: predichos {sw_pred}, reales {sw_true}")
    # error en tiempo: cuánto antes/después se cambia de zona respecto a la verdad
    cm = np.zeros((6, 6), int)
    for r, p in ok:
        cm[r["zone"] - 1, p["reported"] - 1] += 1
    print("confusión (fila = verdad, columna = predicción)")
    print("      " + " ".join(f"Z{j + 1:<4}" for j in range(6)))
    for i in range(6):
        print(f"  Z{i + 1}  " + " ".join(f"{v:<5}" for v in cm[i]))


def ablation(labels, feats, distance, seeds=(0, 1, 2)):
    windows = ((0, 60), (60, 120), (120, 180), (180, 228))
    print(f"{'evidencia':<10} {'cortes':<9} {'total':>6} " + " ".join(f"{a:>3}-{b:<3}s" for a, b in windows) + "  incert.")
    for ev in ("none", "curv", "mem", "mem+curv"):
        for cuts in ("none", "detected", "oracle"):
            if ev == "none" and cuts != "none" and feats is None:
                continue
            accs, wins, stds = [], [], []
            for seed in seeds:
                P = run(labels, cuts, distance, seed, feats, ev)
                ok = np.array([p["reported"] == r["zone"] for r, p in zip(labels, P)])
                t = np.array([r["t_race"] for r in labels])
                accs.append(ok.mean())
                wins.append([ok[(t >= a) & (t < b)].mean() for a, b in windows])
                stds.append(np.mean([p["x_std"] for p in P]))
            w = np.mean(wins, 0)
            print(f"{ev:<10} {cuts:<9} {np.mean(accs):>6.1%} " + " ".join(f"{v:>8.0%}" for v in w)
                  + f"  ±{np.mean(stds):.0f} m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("--cuts", choices=["none", "oracle", "detected"], default="none")
    ap.add_argument("--distance", type=float, default=1500)
    ap.add_argument("--features")
    ap.add_argument("--evidence", default="none", choices=["none", "mem", "curv", "mem+curv"])
    ap.add_argument("--ablation", action="store_true", help="tabla con todas las combinaciones")
    ap.add_argument("--out")
    a = ap.parse_args()
    labels = [json.loads(l) for l in open(a.labels)]
    labels.sort(key=lambda r: r["t_race"])
    feats = load_features(a.features) if a.features else None
    if a.ablation:
        ablation(labels, feats, a.distance)
        return
    preds = run(labels, a.cuts, a.distance, feats=feats, evidence=a.evidence)
    report(labels, preds)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w") as f:
            for r, p in zip(labels, preds):
                f.write(json.dumps({**p, "t_video": r["t_video"], "truth": r.get("zone")}) + "\n")


if __name__ == "__main__":
    main()
