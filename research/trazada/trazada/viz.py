"""Dibujos de depuración: líneas de pista reproyectadas, corredores y vista cenital."""
from __future__ import annotations

import colorsys

import cv2
import numpy as np

from .calibration import Calibration
from .geometry import STANDARD, Track


def id_color(i: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.75, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


def _project(calib: Calibration, xy: np.ndarray, w: int, h: int):
    """Mundo -> imagen, descartando puntos detrás de la cámara o muy fuera de cuadro."""
    Hi = calib.H_inv
    p = np.c_[xy, np.ones(len(xy))] @ Hi.T
    ok = p[:, 2] > 1e-9
    uv = p[:, :2] / p[:, 2:3]
    ok &= (uv[:, 0] > -w) & (uv[:, 0] < 2 * w) & (uv[:, 1] > -h) & (uv[:, 1] < 2 * h)
    return uv, ok


def draw_track_overlay(img, calib: Calibration, track: Track = STANDARD, step: float = 0.5):
    """Pinta las líneas de pista sobre el video. Si no calzan con las reales, la calibración está mal."""
    h, w = img.shape[:2]
    s = np.arange(0, track.lap + step, step)
    over = img.copy()
    for k in range(track.lanes + 1):
        x, y = track.track_to_world(s, np.full_like(s, k * track.lane_width))
        uv, ok = _project(calib, np.c_[x, y], w, h)
        _polyline_masked(over, uv, ok, (255, 255, 255) if k else (0, 200, 255), 2 if k == 0 else 1)
    # meta y marcas cada 50 m sobre el bordillo
    for sm in np.arange(0, track.lap, 50):
        x, y = track.track_to_world(np.array([sm, sm]), np.array([0, track.lanes * track.lane_width]))
        uv, ok = _project(calib, np.c_[x, y], w, h)
        if ok.all():
            cv2.line(over, tuple(map(int, uv[0])), tuple(map(int, uv[1])), (0, 140, 255), 1, cv2.LINE_AA)
            cv2.putText(over, f"{int(sm)}m", tuple(map(int, uv[0])), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1, cv2.LINE_AA)
    cv2.addWeighted(over, 0.55, img, 0.45, 0, dst=img)
    for p in calib.image_pts:
        cv2.drawMarker(img, (int(p[0]), int(p[1])), (0, 255, 255), cv2.MARKER_CROSS, 14, 2)


def _polyline_masked(img, uv, ok, color, thick):
    run = []
    for p, good in zip(uv, ok):
        if good:
            run.append(p)
        elif run:
            _pl(img, run, color, thick)
            run = []
    if run:
        _pl(img, run, color, thick)


def _pl(img, pts, color, thick):
    if len(pts) > 1:
        cv2.polylines(img, [np.int32(np.round(pts))], False, color, thick, cv2.LINE_AA)


def draw_runners(img, runners, trails: dict | None = None):
    for r in runners:
        c = id_color(r.id)
        x1, y1, x2, y2 = map(int, r.bbox)
        cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
        cv2.circle(img, (int(r.px[0]), int(r.px[1])), 5, c, -1)
        if trails is not None and r.id in trails and len(trails[r.id]) > 1:
            cv2.polylines(img, [np.int32(trails[r.id])], False, c, 2, cv2.LINE_AA)
        lab = f"#{r.id} P{r.rank} pista {r.lane} {r.speed:4.1f}m/s +{max(0, r.extra):.1f}m"
        (tw, th), _ = cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 6, y1), (20, 20, 20), -1)
        cv2.putText(img, lab, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)


class TopView:
    """Vista cenital centrada en la zona que ve la cámara."""

    def __init__(self, calib: Calibration, track: Track = STANDARD, size=(420, 420), pad_m: float = 10.0):
        self.track, self.size = track, size
        pts = np.asarray(calib.world_pts) if calib.world_pts else np.array([[-60, -45], [60, 45]])
        lo, hi = pts.min(0) - pad_m, pts.max(0) + pad_m
        self.lo, self.scale = lo, min(size[0] / (hi[0] - lo[0]), size[1] / (hi[1] - lo[1]))
        self.base = np.full((size[1], size[0], 3), (40, 60, 45), np.uint8)
        s = np.arange(0, track.lap + 0.5, 0.5)
        outer = np.c_[track.track_to_world(s, np.full_like(s, track.lanes * track.lane_width))]
        inner = np.c_[track.track_to_world(s, np.zeros_like(s))]
        poly = np.vstack([self._px(np.c_[outer[0], outer[1]]), self._px(np.c_[inner[0], inner[1]])[::-1]])
        cv2.fillPoly(self.base, [np.int32(poly)], (58, 67, 168))
        for k in range(track.lanes + 1):
            x, y = track.track_to_world(s, np.full_like(s, k * track.lane_width))
            cv2.polylines(self.base, [np.int32(self._px(np.c_[x, y]))], False, (235, 235, 235), 1, cv2.LINE_AA)

    def _px(self, xy):
        xy = np.atleast_2d(xy)
        return np.c_[(xy[:, 0] - self.lo[0]) * self.scale, self.size[1] - (xy[:, 1] - self.lo[1]) * self.scale]

    def render(self, runners, trails_world: dict | None = None):
        img = self.base.copy()
        if trails_world:
            for i, pts in trails_world.items():
                if len(pts) > 1:
                    cv2.polylines(img, [np.int32(self._px(np.asarray(pts)))], False, id_color(i), 2, cv2.LINE_AA)
        for r in runners:
            p = self._px([r.x, r.y])[0]
            cv2.circle(img, (int(p[0]), int(p[1])), 6, id_color(r.id), -1)
            cv2.circle(img, (int(p[0]), int(p[1])), 6, (15, 15, 15), 1)
            cv2.putText(img, str(r.id), (int(p[0]) + 7, int(p[1]) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        return img
