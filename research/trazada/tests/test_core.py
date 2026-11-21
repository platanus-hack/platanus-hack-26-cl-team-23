import math

import numpy as np
import pytest

from trazada.calibration import fit, track_pts_to_world
from trazada.filters import RunnerFilter
from trazada.geometry import STANDARD as T


def test_lap_is_400m():
    assert T.lap == pytest.approx(400.0, abs=0.01)


@pytest.mark.parametrize("s", [0, 10, 57.8, 115.6, 150, 200, 260, 330, 399.9])
@pytest.mark.parametrize("d", [0, 0.3, 1.22, 5.0])
def test_roundtrip(s, d):
    x, y = T.track_to_world(s, d)
    s2, d2 = T.world_to_track(x, y)
    assert T.ds_wrap(s, s2) == pytest.approx(0, abs=1e-6)
    assert d2 == pytest.approx(d, abs=1e-6)


def test_landmarks():
    # meta: fin de la recta principal, sobre el bordillo
    x, y = T.track_to_world(0, 0)
    assert (x, y) == pytest.approx((T.straight / 2, -T.radius))
    # mitad de la curva 1: punto más a la derecha
    x, y = T.track_to_world(T.curve_len / 2, 0)
    assert (x, y) == pytest.approx((T.straight / 2 + T.radius, 0), abs=1e-9)
    assert T.segment(10) == "curva1" and T.segment(150) == "recta_opuesta" and T.segment(390) == "recta_principal"
    assert T.lane_of(0.1) == 1 and T.lane_of(1.3) == 2 and T.lane_of(-0.5) == 0


def test_homography_recovers_meters():
    # cámara inventada: homografía mundo->imagen conocida, se recupera desde 6 puntos
    G = np.array([[8.0, 2.0, 600], [0.5, -3.0, 500], [0.002, 0.004, 1]])
    sd = [(0, 0), (0, 9.76), (20, 0), (20, 9.76), (40, 4.88), (10, 2.44)]
    world = track_pts_to_world(sd)
    p = np.c_[world, np.ones(len(world))] @ G.T
    img = p[:, :2] / p[:, 2:]
    cal = fit(img, world, (1920, 1080))
    assert cal.rms_m < 1e-3
    probe = track_pts_to_world([(30, 1.5)])
    pp = np.c_[probe, [1]] @ G.T
    back = cal.img_to_world(pp[:, :2] / pp[:, 2:])
    assert back == pytest.approx(probe, abs=1e-3)


def test_filter_speed_and_extra_distance():
    # corredor a 6.5 m/s de progreso por la curva 1, en pista 2 (d = 1.5), con ruido
    rng = np.random.default_rng(0)
    f, v, d = RunnerFilter(), 6.5, 1.5
    for k in range(300):
        t = k / 30
        s, dd, sp = f.update(5 + v * t + rng.normal(0, 0.15), d + rng.normal(0, 0.1), t)
    assert sp == pytest.approx(v, abs=0.2)
    # metros extra esperados: progreso * ((R + d) / (R + 0.3) - 1)
    expect = (v * 299 / 30) * ((T.radius + d) / T.r_meas - 1)
    assert f.extra == pytest.approx(expect, rel=0.15)


def test_filter_wraps_at_finish_line():
    f = RunnerFilter()
    for k in range(60):
        t = k / 30
        f.update((395 + 7 * t) % 400, 0.3, t)
    assert f.s.v == pytest.approx(7, abs=0.3)
    assert f.progress == pytest.approx(7 * 59 / 30, abs=0.5)


# ------------------------------------------------------------------ zonas
from trazada.zones import start_s, zone_edges, zone_of, zone_sequence
from trazada.zone_filter import ZoneFilter, ZoneReporter


def test_zone_edges_and_lookup():
    e = zone_edges()
    assert e[-1] == pytest.approx(T.lap)
    assert np.allclose(np.diff(e)[[0, 1, 3, 4]], T.curve_len / 2)
    assert [zone_of(s) for s in (0, 57, 60, 116, 199, 201, 260, 316, 399.9, T.lap, -1)] == [1, 1, 2, 3, 3, 4, 5, 6, 6, 1, 6]


@pytest.mark.parametrize("dist,s0", [(1500, 100), (5000, 200), (800, 0), (10000, 0), (3000, 200)])
def test_start_position(dist, s0):
    assert start_s(dist) == pytest.approx(s0, abs=0.05) or start_s(dist) == pytest.approx(400, abs=0.05) and s0 == 0


def test_1500_zone_sequence():
    seq = zone_sequence(1500)
    assert seq[:5] == [2, 3, 4, 5, 6] and seq[5:] == [1, 2, 3, 4, 5, 6] * 3 and len(seq) == 23


def test_prior_filter_moves_forward_and_stays_put_before_gun():
    zf = ZoneFilter(1500, n=2000)
    zf.predict(-5.0)
    assert zone_of(zf.estimate()["s"]) == 2 and zf.estimate()["x"] == 0
    zf.predict(5.0)            # ~33 m: recta opuesta
    assert zf.estimate()["zone"] == 3
    zf.predict(60.0)           # ~400 m recorridos: de vuelta cerca de la salida
    assert 330 < zf.estimate()["x"] < 470


def test_filter_update_pulls_to_evidence():
    zf = ZoneFilter(1500, n=4000)
    zf.predict(150.0)          # incertidumbre grande
    before = zf.zone_probs().max()
    zf.update(lambda s: np.where(zone_of(s) == 4, 1.0, 0.05))
    assert zf.estimate()["zone"] == 4 and zf.zone_probs().max() > before


def test_reporter_hysteresis():
    rep = ZoneReporter(p_min=0.6, hold=3)
    p = lambda z, q: np.eye(6)[z - 1] * q + (1 - q) / 6
    assert rep(p(2, 0.9)) == 2
    assert rep(p(3, 0.9)) == 2 and rep(p(3, 0.9)) == 2 and rep(p(3, 0.9)) == 3
    assert rep(p(4, 0.25)) == 3     # no supera p_min ni le gana a la actual por el margen


# ------------------------------------------------------------------ evidencia visual
import cv2

from trazada.evidence import CameraMemory, curvature_likelihood, descriptor, line_curvature
from trazada.shots import ShotDetector


def _scene(seed=0, shift=0):
    rng = np.random.default_rng(seed)
    img = np.zeros((720, 1280, 3), np.uint8)
    img[:300] = rng.integers(0, 255, 3)            # "tribuna"
    img[300:] = (40, 40, 190)                       # tartán (BGR)
    img = np.roll(img + rng.integers(0, 20, img.shape, dtype=np.uint8), shift, axis=1)
    return img


def test_shot_detector_cut_vs_pan():
    sd = ShotDetector()
    assert not sd(_scene(0), 0.0)
    assert not sd(_scene(0, shift=40), 0.033)      # paneo
    assert sd(np.full((720, 1280, 3), (60, 160, 60), np.uint8), 0.066)   # otro plano (pasto)


def _lines(curved: bool):
    img = np.zeros((720, 1280, 3), np.uint8)
    img[:] = (40, 40, 190)
    for k in range(5):
        if curved:
            cv2.ellipse(img, (640, 1400), (900 + 90 * k, 1100 + 90 * k), 0, 200, 340, (255, 255, 255), 5)
        else:
            cv2.line(img, (0, 150 + 70 * k), (1279, 250 + 70 * k), (255, 255, 255), 5)
    return img


def test_line_curvature_straight_vs_curve():
    st, cu = line_curvature(_lines(False)), line_curvature(_lines(True))
    assert st["n"] >= 3 and cu["n"] >= 3
    assert st["bend"] < 0.005 < 0.02 < cu["bend"]
    lik = curvature_likelihood(cu)
    assert lik(np.array([30.0]))[0] > lik(np.array([150.0]))[0]       # curva 1 > recta opuesta


def test_camera_memory_recalls_only_past_laps():
    mem = CameraMemory()
    a, b = descriptor(_scene(1)), descriptor(_scene(2))
    for k in range(6):
        mem.add(a, 150.0 + k, 3.0, t=float(k))
        mem.add(b, 330.0 + k, 3.0, t=float(k))
    assert mem.likelihood(a, t=10.0) is None             # muy reciente: no cuenta como recuerdo
    lik = mem.likelihood(a, t=70.0)
    v = lik(np.array([152.0, 332.0, 40.0]))
    assert v[0] > v[1] and v[0] > v[2]
    assert not mem.add(a, 10.0, 50.0, t=80.0)            # muy incierto: no se guarda
