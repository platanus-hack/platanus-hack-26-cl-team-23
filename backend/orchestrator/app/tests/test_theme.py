import numpy as np
import pytest

from app.cv import theme as th


def test_colores():
    assert th.rgb("orange") == (255, 91, 20)
    assert th.bgr("orange") == (20, 91, 255)
    assert th.bgr("#1D1D1F") == th.INK


def test_cifras_a_la_chilena():
    assert th.fmt_num(3.2, 1, "m", sign=True) == "+3,2 m"
    assert th.fmt_num(1188, 0, "m") == "1.188 m"
    assert th.fmt_num(0.5, 2, "s") == "0,50 s"


def test_escala():
    assert th.Scale(1080).size("label") == 22
    assert th.Scale(720).px(30) == 20
    assert th.Scale(2160).px(4) == 8


def test_fuentes_existen():
    for p in th.FONTS.values():
        assert p.exists(), p


@pytest.mark.parametrize("h", [720, 1080])
def test_piezas_dibujan_sin_salirse(h):
    w = h * 16 // 9
    img = np.full((h, w, 3), 90, np.uint8)
    sc = th.Scale(h)
    before = img.copy()
    th.text(img, (10, 10), "Zona enfocada", sc, role="label")
    th.text(img, (w - 5, h - 5), "fuera de borde 312 m", sc, role="figure", anchor="lt")  # recorta
    th.pill(img, (100, 100), "#7", sc, chosen=True)
    th.pill(img, (-20, -20), "3", sc, role="label")  # recorta
    th.corners(img, (200, 200, 260, 340), sc, chosen=False)
    th.trail(img, [(300, 300), (320, 305), (340, 309), (360, 312)] * 3, sc, chosen=True)
    th.glass_panel(img, (w - 400, h - 300, 450, 350), sc)  # recorta
    th.oval(
        img, (50, 400 * h // 1080, 320, 200), sc, zone=3, s_est=150, s_sd=9, runners_s=[140, 160]
    )
    assert img.shape == before.shape and img.dtype == np.uint8
    assert (img != before).any()


def test_pildora_elegida_es_naranja_con_tinta():
    img = np.zeros((200, 400, 3), np.uint8)
    sc = th.Scale(1080)
    x1, y1, x2, y2 = th.pill(img, (20, 20), "#1", sc, chosen=True, anchor="lt")
    # el borde izquierdo-medio de la píldora es naranja puro; nunca texto blanco
    assert tuple(img[(y1 + y2) // 2, x1 + 4 + (y2 - y1) // 2 - 6]) == th.ORANGE
    assert not (img[y1:y2, x1:x2] == 255).all(axis=2).any()


def test_fundido_y_suavizado():
    assert (
        th.fade(0.0, 0.0) == 0.0 and th.fade(0.1, 0.0) == pytest.approx(0.5) and th.fade(1, 0) == 1
    )
    assert th.fade(0.95, 0.0, t_out=1.0) == pytest.approx(0.25)
    sm = th.Smoother(tau=0.2)
    assert sm(1, [0, 0], 0.0).tolist() == [0, 0]
    v = sm(1, [10, 0], 0.1)
    assert 0 < v[0] < 10  # se mueve hacia el valor nuevo, sin saltar
    assert sm(1, [10, 0], 5.0)[0] == 10  # después de una pausa larga reinicia
