"""Zona enfocada por la cámara: extracción de evidencia por frame y filtro sobre la secuencia.

Dos etapas, igual que detect -> track:
  frame_features(frame)  sin estado, por frame (se puede paralelizar y repartir en lotes)
  run(frames, ...)       con estado, sobre las features acumuladas (barato; es determinista)
"""

from dataclasses import dataclass, field

import numpy as np

from app.cv.zones.evidence import (
    CameraMemory,
    CutDetector,
    curvature_likelihood,
    descriptor,
    line_curvature,
    shot_hist,
)
from app.cv.zones.filter import ZoneFilter, ZoneReporter


@dataclass
class FrameFeatures:
    t: float
    hist: np.ndarray
    desc: np.ndarray | None = None
    bend: float | None = None
    chord: float | None = None
    n: int | None = None


@dataclass
class ZoneParams:
    distance: float = 1500
    t0: float = 0.0
    seed: int = 0
    cut_threshold: float = 0.19
    sample_s: float = 0.5
    particles: int = 4000


@dataclass
class ZoneOutput:
    frames: list[dict] = field(default_factory=list)
    cuts: list[float] = field(default_factory=list)


def frame_features(frame: np.ndarray) -> dict:
    curv = line_curvature(frame)
    return {
        "hist": shot_hist(frame),
        "desc": descriptor(frame),
        "bend": curv["bend"],
        "chord": curv["chord"],
        "n": curv["n"],
    }


def run(features: list[FrameFeatures], params: ZoneParams) -> ZoneOutput:
    """Recorre los frames en orden usando solo presente y pasado (como en vivo).

    El corte se detecta en cada frame; la evidencia de curvatura y de memoria entra cada
    `sample_s` segundos de carrera, ya con el reloj en t - t0.
    """
    zf = ZoneFilter(params.distance, n=params.particles, seed=params.seed)
    reporter, memory = ZoneReporter(), CameraMemory()
    cuts_detector = CutDetector(params.cut_threshold)
    times = np.array([f.t for f in features])
    tol = 0.5 * float(np.median(np.diff(times))) if len(times) > 1 else 0.0

    out = ZoneOutput()
    next_sample, cut_pending, recognized, reported = 0.0, False, False, None
    for i, f in enumerate(features):
        t = f.t - params.t0
        is_cut = cuts_detector(f.hist, t)
        if is_cut:
            cut_pending = True
            out.cuts.append(round(f.t, 3))
        zf.predict(t)

        if t >= 0 and t >= next_sample - tol:
            if cut_pending:
                zf.on_cut()
                cut_pending = False
            if f.n is not None and f.bend is not None and f.chord is not None:
                lik = curvature_likelihood(f.bend, f.chord, f.n)
                if lik is not None:
                    zf.update(lik)
            recognized = False
            if f.desc is not None:
                lik = memory.likelihood(f.desc, t)
                recognized = lik is not None
                if lik is not None:
                    zf.update(lik)
            est = zf.estimate()
            reported = reporter(np.array(est["p"]))
            if f.desc is not None:
                memory.add(f.desc, est["s"], est["x_std"], t)
            while next_sample - tol <= t:
                next_sample += params.sample_s

        est = zf.estimate()
        out.frames.append(
            {
                "frame": i,
                "t": round(f.t, 3),
                "zone": reported if reported is not None else est["zone"],
                "p": est["p"],
                "s": est["s"],
                "x": est["x"],
                "x_std": est["x_std"],
                "v": est["v"],
                "cut": is_cut,
                "recognized": recognized,
            }
        )
    return out
