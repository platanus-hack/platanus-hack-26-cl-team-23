"""Posición y velocidad de cada atleta respecto a la cancha, en video de TV.

Triangulación:
    posición atleta  = posición del grupo (filtro de zonas: metros de la cabeza de carrera)
                     + posición relativa al grupo (medida dentro de cada frame)
    velocidad atleta = velocidad del grupo + velocidad relativa al grupo

Dos etapas, igual que detect -> track y zones/features -> zones:
  frame_features(...)  sin estado, por lote de frames: mide Δs y d de cada corredor y el
                       movimiento del fondo entre frames consecutivos del lote
  run(...)             con estado, sobre las features acumuladas + la salida de /zones
"""

import math
from dataclasses import dataclass, field

import numpy as np

from app.cv.athletes.measure import (
    LANE,
    background_shift,
    jersey_hist,
    measure_frame,
    motion_gray,
)
from app.cv.athletes.tracker import AthleteTracker, stable_order
from app.cv.zones.track import STANDARD


@dataclass
class RunnerFeatures:
    id: int | None  # id del tracker de imagen (/track)
    bbox: list[float]
    foot: list[float]
    ds: float  # m relativo al centro del grupo, en el sentido de u_img
    sigma_ds: float
    d: float | None  # m al bordillo
    sigma_d: float | None
    jersey: np.ndarray | None


@dataclass
class AthleteFrameFeatures:
    t: float
    u_img: list[float] | None  # dirección de imagen sobre la que se midió ds
    head_on: bool = False
    blind: bool = False
    bg_shift: list[float] | None = None  # movimiento del fondo desde el frame anterior (px)
    runners: list[RunnerFeatures] = field(default_factory=list)


@dataclass
class GroupState:
    x: float  # metros recorridos por la cabeza de carrera (salida de /zones)
    v: float  # su velocidad (m/s)
    cut: bool = False


@dataclass
class AthleteParams:
    t0: float = 0.0
    field_size: int = 12
    min_bg_dt: float = 0.25  # s: más separados que esto, el desplazamiento del fondo no sirve


def frame_features(frames: list[np.ndarray], times: list[float], boxes: list[list[list[float]]]):
    """Mide un lote de frames consecutivos. boxes por frame: [[id, x1, y1, x2, y2], ...] en
    píxeles del frame (id = -1 si no hay). -> list[AthleteFrameFeatures]"""
    out, prev_gray, prev_t = [], None, None
    for frame, t, fb in zip(frames, times, boxes, strict=True):
        arr = np.asarray(fb, float).reshape(-1, 5)
        geo, meas = measure_frame(frame, arr[:, 1:5])
        gray = motion_gray(frame)
        shift = None
        if prev_gray is not None and t - prev_t <= AthleteParams.min_bg_dt:
            shift = background_shift(prev_gray, gray, frame.shape)
        prev_gray, prev_t = gray, t
        runners = []
        for m in meas:
            row = arr[m["idx"]]
            runners.append(
                RunnerFeatures(
                    id=None if row[0] < 0 else int(row[0]),
                    bbox=[float(v) for v in row[1:5]],
                    foot=m["foot"],
                    ds=m["ds"],
                    sigma_ds=m["sigma_ds"],
                    d=m["d"],
                    sigma_d=m["sigma_d"],
                    jersey=jersey_hist(frame, row[1:5]),
                )
            )
        out.append(
            AthleteFrameFeatures(
                t=t,
                u_img=None if geo is None else [float(geo.u_img[0]), float(geo.u_img[1])],
                head_on=bool(geo is not None and geo.head_on),
                blind=bool(geo is not None and geo.blind),
                bg_shift=shift,
                runners=runners,
            )
        )
    return out


def lane_of(d: float) -> int:
    return int(min(9, max(0.0, d) // LANE + 1))


def run(
    features: list[AthleteFrameFeatures], group: list[GroupState], params: AthleteParams
) -> list[dict]:
    """Recorre los frames en orden usando solo presente y pasado (como en vivo).

    "Adelante" en cada plano: el movimiento de los corredores respecto al fondo (la cámara los
    sigue, así que el fondo se mueve al revés). De frente, adelante es hacia la cámara.
    """
    tracker = AthleteTracker(field_size=params.field_size)
    frames_out: list[dict] = []
    fwd: np.ndarray | None = None
    prev_feet: dict[int, np.ndarray] = {}
    prev_order: list[int] = []
    for i, (f, g) in enumerate(zip(features, group, strict=True)):
        t_race = f.t - params.t0
        if g.cut:
            fwd, prev_feet = None, {}
        feet = {r.id: np.array(r.foot) for r in f.runners if r.id is not None}
        if f.bg_shift is not None and not g.cut:
            rel = [feet[k] - prev_feet[k] - np.array(f.bg_shift) for k in feet if k in prev_feet]
            if rel:
                mv = np.median(rel, 0)
                norm = float(np.linalg.norm(mv))
                if norm > 0.5:
                    mv = mv / norm
                    fwd = mv if fwd is None else 0.8 * fwd + 0.2 * mv
        prev_feet = feet

        live = []
        tracker.predict(f.t, g.v if t_race >= 0 else 0.0)
        if t_race >= 0 and f.u_img is not None and f.runners:
            if f.head_on:
                sign = 1.0
            elif fwd is not None and abs(float(np.dot(fwd, f.u_img))) > 0.2:
                sign = 1.0 if float(np.dot(fwd, f.u_img)) > 0 else -1.0
            else:
                sign = 0.0  # todavía no se sabe hacia dónde es adelante en este plano
            meas = [
                {
                    "ds": sign * r.ds,
                    "sigma_ds": r.sigma_ds if sign else 1e6,
                    "d": r.d,
                    "sigma_d": r.sigma_d,
                    "bbox": r.bbox,
                }
                for r in f.runners
            ]
            live = tracker.update(
                f.t,
                max(g.x, 0.0),
                meas,
                [r.id for r in f.runners],
                [r.jersey for r in f.runners],
                cut=g.cut,
            )

        recent = [a for a in tracker.ath.values() if f.t - a.last_t < 3.0]
        order = stable_order(recent, prev_order)
        prev_order = [a.id for a in order]
        live_ids = {a.id for a in live}
        frames_out.append(
            {
                "frame": i,
                "t": round(f.t, 3),
                "group": {"x": round(g.x, 1), "v": round(g.v, 2)},
                "measured": bool(f.u_img is not None and not f.blind),
                "athletes": [
                    {
                        "id": a.id,
                        "track_id": a.tid if a.id in live_ids else None,
                        "rank": k + 1,
                        "x": round(a.x, 2),
                        "s": round(a.x % STANDARD.lap, 2),
                        "d": round(a.d, 2),
                        "lane": lane_of(a.d),
                        "v": round(g.v + a.u, 2),
                        "u": round(a.u, 2),
                        "visible": a.id in live_ids,
                        "sigma_x": round(math.sqrt(max(a.P[0, 0], 0.0)), 2),
                        "bbox": [round(v, 1) for v in a.box]
                        if a.id in live_ids and a.box
                        else None,
                    }
                    for k, a in enumerate(order)
                ],
            }
        )
    return frames_out
