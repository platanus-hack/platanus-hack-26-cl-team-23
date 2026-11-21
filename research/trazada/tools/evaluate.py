#!/usr/bin/env python
"""Compara posiciones estimadas (run.py --jsonl) con la verdad de terreno (make_synthetic.py).

Uso: python -m tools.evaluate out/synth_pos.jsonl out/synth_truth.jsonl
Reporta por corredor: cobertura, error en s y d, pista correcta y cambios de ID.
"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np

from trazada.geometry import STANDARD as T


def main(pred_path, truth_path, gate_m=1.5):
    truth = defaultdict(dict)
    for line in open(truth_path):
        r = json.loads(line)
        truth[r["frame"]][r["id"]] = r
    pred = {}
    for line in open(pred_path):
        m = json.loads(line)
        pred[m["frame"]] = m["runners"]

    stats = defaultdict(lambda: dict(n=0, hit=0, es=[], ed=[], lane_ok=0, ids=[]))
    for f, gt in truth.items():
        ps = pred.get(f, [])
        # emparejamiento 1 a 1 (codicioso por distancia): una detección no puede ser dos corredores
        cand = sorted((np.hypot(T.ds_wrap(g["s"], p["s"]), g["d"] - p["d"]), gid, j)
                      for gid, g in gt.items() for j, p in enumerate(ps))
        match, used = {}, set()
        for dist, gid, j in cand:
            if dist <= gate_m and gid not in match and j not in used:
                match[gid] = j
                used.add(j)
        for gid, g in gt.items():
            st = stats[gid]
            st["n"] += 1
            if gid not in match:
                continue
            p = ps[match[gid]]
            st["hit"] += 1
            st["es"].append(T.ds_wrap(g["s"], p["s"]))
            st["ed"].append(p["d"] - g["d"])
            st["lane_ok"] += T.lane_of(g["d"]) == p["lane"]
            st["ids"].append(p["id"])

    print(f"{'corr':>4} {'cobert':>7} {'err s (m)':>14} {'err d (m)':>14} {'pista ok':>9} {'IDs':>5}")
    for gid in sorted(stats):
        st = stats[gid]
        es, ed = np.array(st["es"] or [np.nan]), np.array(st["ed"] or [np.nan])
        switches = sum(1 for a, b in zip(st["ids"], st["ids"][1:]) if a != b)
        print(f"{gid:>4} {st['hit'] / st['n']:>7.0%} {np.mean(es):>+6.2f}±{np.std(es):<5.2f}  {np.mean(ed):>+6.2f}±{np.std(ed):<5.2f}"
              f" {st['lane_ok'] / max(1, st['hit']):>9.0%} {len(Counter(st['ids'])):>3} ({switches} cambios)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
