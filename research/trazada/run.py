#!/usr/bin/env python
"""Posición en tiempo real de cada corredor.

Uso:
  python run.py --source video.mp4 --calib calib.json --show
  python run.py --source 0 --calib calib.json --show --ws 8765        # en vivo, transmite al front
  python run.py --source video.mp4 --calib calib.json --save out.mp4 --jsonl pos.jsonl

Teclas en la ventana: espacio = pausa · o = líneas de pista on/off · r = reiniciar IDs · q = salir
"""
import argparse
import time
from collections import defaultdict, deque

import cv2
import numpy as np

from trazada.calibration import Calibration
from trazada.pipeline import RunnerLocator, VideoSource
from trazada.viz import TopView, draw_runners, draw_track_overlay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="archivo, índice de cámara o URL rtsp/http")
    ap.add_argument("--calib", required=True)
    ap.add_argument("--model", default="yolo26n.pt", help="p. ej. yolo26s.pt, o yolo26n-pose.pt para usar tobillos")
    ap.add_argument("--tracker", default="bytetrack_runners.yaml", help="o botsort.yaml / ocsort.yaml")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default=None)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save", help="guardar video anotado (mp4)")
    ap.add_argument("--jsonl", help="guardar posiciones por frame")
    ap.add_argument("--ws", type=int, help="puerto WebSocket para transmitir posiciones")
    ap.add_argument("--max-frames", type=int, default=0)
    a = ap.parse_args()

    cal = Calibration.load(a.calib)
    src = VideoSource(a.source)
    loc = RunnerLocator(cal, model=a.model, tracker=a.tracker, imgsz=a.imgsz, conf=a.conf, device=a.device)
    print(f"Modelo {a.model} ({'pose' if loc.is_pose else 'detección'}) en {loc.device} · fuente {'en vivo' if src.live else 'archivo'}")

    sinks = []
    if a.jsonl:
        from trazada.stream import JsonlWriter
        sinks.append(JsonlWriter(a.jsonl))
    if a.ws:
        from trazada.stream import WebSocketBroadcaster
        sinks.append(WebSocketBroadcaster(port=a.ws))

    top = TopView(cal)
    trails_px = defaultdict(lambda: deque(maxlen=90))
    trails_w = defaultdict(lambda: deque(maxlen=150))
    writer, overlay, paused = None, True, False
    times = deque(maxlen=30)

    try:
        while True:
            if paused:
                k = cv2.waitKey(30) & 0xFF
                paused = k != ord(" ")
                if k == ord("q"):
                    break
                continue
            frame, t = src.read()
            if frame is None:
                break
            t0 = time.perf_counter()
            runners = loc.process(frame, t)
            times.append(time.perf_counter() - t0)

            msg = {"t": round(t, 3), "frame": src.idx, "runners": [r.to_json() for r in runners]}
            for s in sinks:
                s.send(msg)

            if a.show or a.save:
                vis = frame.copy()
                if overlay:
                    draw_track_overlay(vis, loc.calib)
                for r in runners:
                    trails_px[r.id].append(r.px)
                    trails_w[r.id].append((r.x, r.y))
                draw_runners(vis, runners, trails_px)
                fps = len(times) / max(1e-6, sum(times))
                cv2.putText(vis, f"{fps:5.1f} fps  {len(runners)} corredores", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
                tv = top.render(runners, trails_w)
                th = vis.shape[0]
                tv = cv2.resize(tv, (int(tv.shape[1] * th / tv.shape[0]), th))
                out = np.hstack([vis, tv])
                if a.save:
                    if writer is None:
                        writer = cv2.VideoWriter(a.save, cv2.VideoWriter_fourcc(*"mp4v"), src.fps, (out.shape[1], out.shape[0]))
                    writer.write(out)
                if a.show:
                    cv2.imshow("TRAZADA", out)
                    k = cv2.waitKey(1) & 0xFF
                    if k == ord("q"):
                        break
                    if k == ord(" "):
                        paused = True
                    if k == ord("o"):
                        overlay = not overlay
                    if k == ord("r"):
                        loc.reset(); trails_px.clear(); trails_w.clear()
            if a.max_frames and src.idx + 1 >= a.max_frames:
                break
    finally:
        src.release()
        if writer:
            writer.release()
        for s in sinks:
            s.close()
        cv2.destroyAllWindows()
    if times:
        print(f"Procesamiento medio: {1000 * np.mean(times):.1f} ms/frame ({1 / np.mean(times):.1f} fps)")


if __name__ == "__main__":
    main()
