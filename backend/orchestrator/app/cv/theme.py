"""Tema "Pista" para dibujar sobre video (OpenCV + PIL).

Traduce el sistema de diseño de TRAZADA (DESIGN.md) a funciones de dibujo listas para usar
sobre un cuadro BGR de OpenCV. Todo se escala por el alto del video (base 1080p), así el
mismo código se ve igual en 720p o 4K.

Uso típico:

    from app.cv import theme as th

    sc = th.Scale(frame.shape[0])                   # escala del video
    th.corners(frame, bbox, sc, chosen=(tid == elegido))
    th.pill(frame, (x1, y1 - sc.px(8)), f"#{tid}", sc, chosen=..., anchor="lb")
    th.trail(frame, puntos, sc, chosen=...)
    x, y, w, h = th.glass_panel(frame, (x0, y0, w, h), sc)
    th.text(frame, (x + sc.px(24), y + sc.px(24)), "Zona enfocada", sc, role="label")

Reglas (resumen de DESIGN.md):
  - Naranja = el corredor elegido, uno por pantalla. El resto, blanco/grises.
  - Verde / rojo solo para ganó / perdió.
  - Texto con fuentes reales (Inter, Geist Mono), nunca Hershey. Nunca texto blanco sobre naranja.
  - Paneles de vidrio esmerilado (desenfoque + blanco 72 %), nunca negros opacos.

No depende de nada más del paquete: se puede copiar tal cual (por ejemplo a research/trazada/
para los scripts locales). Requiere numpy, opencv y Pillow (Pillow ya llega con supervision).
Fuentes en ./fonts (Inter y Geist Mono, licencia SIL OFL 1.1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------------------
# Color
# --------------------------------------------------------------------------------------

HEX = {
    "bg": "#F5F5F7",  # fondo de la app
    "surface": "#FFFFFF",  # tarjetas, píldoras
    "line": "#E5E5EA",  # divisiones
    "ink": "#1D1D1F",  # texto principal, zona actual en el óvalo
    "ink_soft": "#6E6E73",  # texto secundario, rótulos
    "orange": "#FF5B14",  # EL protagonista (uno por pantalla)
    "orange_text": "#C2410C",  # naranja como texto chico sobre blanco
    "cost": "#FFD8C4",  # franja de costo / incertidumbre suave
    "other": "#8E8E93",  # resto de corredores
    "win": "#1A7F37",  # ganó puestos
    "lose": "#D70015",  # perdió puestos
    "lane_a": "#E8E8ED",  # carriles del óvalo (alternados)
    "lane_b": "#DEDEE3",
    "white": "#FFFFFF",
}


def rgb(name_or_hex: str) -> tuple[int, int, int]:
    """Color para PIL (R, G, B). Acepta un nombre de HEX o un '#RRGGBB'."""
    h = HEX.get(name_or_hex, name_or_hex).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def bgr(name_or_hex: str) -> tuple[int, int, int]:
    """Color para OpenCV (B, G, R)."""
    r, g, b = rgb(name_or_hex)
    return b, g, r


# Atajos BGR para OpenCV
INK, INK_SOFT, ORANGE, WHITE = bgr("ink"), bgr("ink_soft"), bgr("orange"), bgr("white")
OTHER, WIN, LOSE, COST = bgr("other"), bgr("win"), bgr("lose"), bgr("cost")

GLASS_ALPHA = 0.72  # blanco del vidrio esmerilado
BOX_ALPHA = 0.80  # esquinas de los no elegidos
TRAIL_ALPHA = 0.50  # estela de los no elegidos

# --------------------------------------------------------------------------------------
# Tipografía
# --------------------------------------------------------------------------------------

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONTS = {
    "text": FONT_DIR / "Inter-Regular.ttf",  # texto corrido
    "strong": FONT_DIR / "Inter-SemiBold.ttf",  # etiquetas de corredor, títulos chicos
    "figure": FONT_DIR / "InterDisplay-Bold.ttf",  # cifras y titulares
    "label": FONT_DIR / "GeistMono-Medium.ttf",  # rótulos MAYÚSCULAS
}

# Tamaños en px a 1080p (se escalan con Scale). Mínimo 22 px a 1080p para que se lea en TV/móvil.
SIZES = {"label": 22, "text": 26, "strong": 26, "title": 36, "figure": 56, "hero": 96}
# Interletra en em por rol (DESIGN.md §2)
TRACKING = {
    "label": 0.08,
    "text": 0.0,
    "strong": 0.0,
    "title": -0.015,
    "figure": -0.03,
    "hero": -0.04,
}
ROLE_FONT = {
    "label": "label",
    "text": "text",
    "strong": "strong",
    "title": "strong",
    "figure": "figure",
    "hero": "figure",
}


@dataclass(frozen=True)
class Scale:
    """Escala relativa al alto del video. Todo lo que se diseñó a 1080p pasa por px()."""

    height: int

    @property
    def k(self) -> float:
        return self.height / 1080.0

    def px(self, v: float) -> int:
        return max(1, round(v * self.k))

    def size(self, role: str) -> int:
        return self.px(SIZES[role])


@lru_cache(maxsize=64)
def font(role: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS[ROLE_FONT[role]]), px)


def _layout(s: str, f: ImageFont.FreeTypeFont, track_px: float, tabular: bool):
    """Posiciones x de cada carácter. Con tabular=True los dígitos usan un ancho fijo,
    así una cifra que cambia cuadro a cuadro no 'baila'."""
    if not track_px and not tabular:
        return None, f.getlength(s)
    cell = max(f.getlength(d) for d in "0123456789") if tabular else 0
    xs, x = [], 0.0
    for ch in s:
        if tabular and ch.isdigit():
            w = cell
            xs.append(x + (cell - f.getlength(ch)) / 2)
        else:
            w = f.getlength(ch)
            xs.append(x)
        x += w + track_px
    return xs, x - track_px if s else 0.0


def measure(
    s: str, sc: Scale, role: str = "text", size: int | None = None, tabular: bool = False
) -> tuple[int, int]:
    """Ancho y alto (de la caja de mayúsculas) que ocupará el texto."""
    if role == "label":
        s = s.upper()
    px = size or sc.size(role)
    f = font(role, px)
    _, w = _layout(s, f, TRACKING[role] * px, tabular)
    cap = f.getbbox("H")[3] - f.getbbox("H")[1]
    return math.ceil(w), int(cap)


def text(
    frame: np.ndarray,
    xy,
    s: str,
    sc: Scale,
    *,
    role: str = "text",
    size: int | None = None,
    color: str = "ink",
    alpha: float = 1.0,
    anchor: str = "lt",
    tabular: bool = False,
):
    """Escribe texto con antialias sobre un cuadro BGR (in place).

    role: label (Geist Mono, MAYÚSCULAS) · text · strong · title · figure · hero.
    anchor: 2 letras, horizontal l/m/r + vertical t/m/b, medidas sobre la caja de mayúsculas
            (así el texto queda centrado ópticamente dentro de una píldora).
    Devuelve la caja (x1, y1, x2, y2) que ocupó.
    """
    if role == "label":
        s = s.upper()
    px = size or sc.size(role)
    f = font(role, px)
    xs, w = _layout(s, f, TRACKING[role] * px, tabular)
    hb = f.getbbox("H")
    cap_top, cap_h = hb[1], hb[3] - hb[1]
    x, y = xy
    x -= {"l": 0, "m": w / 2, "r": w}[anchor[0]]
    y -= {"t": 0, "m": cap_h / 2, "b": cap_h}[anchor[1]]
    # capa del tamaño justo (con holgura para descendentes y antialias)
    asc, desc = f.getmetrics()
    pad = max(2, px // 4)
    lw, lh = math.ceil(w) + 2 * pad, asc + desc + 2 * pad
    layer = Image.new("L", (lw, lh), 0)
    d = ImageDraw.Draw(layer)
    if xs is None:
        d.text((pad, pad), s, font=f, fill=255)
    else:
        for ch, cx in zip(s, xs):
            d.text((pad + cx, pad), ch, font=f, fill=255)
    ox, oy = round(x) - pad, round(y - cap_top) - pad
    _blend_mask(frame, np.asarray(layer, np.float32) / 255.0 * alpha, ox, oy, bgr(color))
    return int(x), int(y), int(x + w), int(y + cap_h)


# --------------------------------------------------------------------------------------
# Composición (máscaras alfa sobre el cuadro)
# --------------------------------------------------------------------------------------


def _blend_mask(frame, mask, ox, oy, color_bgr):
    """frame = frame*(1-a) + color*a dentro de la región (recorta a los bordes)."""
    H, W = frame.shape[:2]
    mh, mw = mask.shape
    x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + mw, W), min(oy + mh, H)
    if x0 >= x1 or y0 >= y1:
        return
    a = mask[y0 - oy : y1 - oy, x0 - ox : x1 - ox, None]
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    roi = roi * (1 - a) + np.array(color_bgr, np.float32) * a
    frame[y0:y1, x0:x1] = roi.astype(np.uint8)


@lru_cache(maxsize=256)
def _rounded_mask(w: int, h: int, r: int) -> np.ndarray:
    """Máscara 0..1 de un rectángulo redondeado, con antialias (supermuestreo 4x)."""
    ss = 4
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0


def rounded_rect(
    frame, rect, sc: Scale, *, color: str = "surface", alpha: float = 1.0, radius: float = 22
):
    x, y, w, h = map(int, rect)
    r = min(sc.px(radius), w // 2, h // 2)
    _blend_mask(frame, _rounded_mask(w, h, r) * alpha, x, y, bgr(color))


def glass_panel(
    frame, rect, sc: Scale, *, radius: float = 22, blur: float = 28, tint: float = GLASS_ALPHA
):
    """Vidrio esmerilado: desenfoca el video detrás + blanco al 72 % + esquinas redondeadas.
    Reemplaza a los paneles negros opacos. Encima va texto en tinta. Devuelve (x, y, w, h)."""
    H, W = frame.shape[:2]
    x, y, w, h = map(int, rect)
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x0 >= x1 or y0 >= y1:
        return x, y, w, h
    sigma = sc.px(blur) / 2
    m = int(sigma * 3)
    bx0, by0, bx1, by1 = max(x0 - m, 0), max(y0 - m, 0), min(x1 + m, W), min(y1 + m, H)
    blurred = cv2.GaussianBlur(frame[by0:by1, bx0:bx1], (0, 0), sigma)[
        y0 - by0 : y1 - by0, x0 - bx0 : x1 - bx0
    ]
    r = min(sc.px(radius), w // 2, h // 2)
    a = _rounded_mask(w, h, r)[y0 - y : y1 - y, x0 - x : x1 - x, None]
    glass = blurred.astype(np.float32) * (1 - tint) + 255.0 * tint
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a) + glass * a).astype(np.uint8)
    return x, y, w, h


def _over(frame, draw_fn, alpha: float):
    """Dibuja con OpenCV en una copia y la mezcla con opacidad `alpha` (para trazos translúcidos)."""
    if alpha >= 0.999:
        draw_fn(frame)
        return
    layer = frame.copy()
    draw_fn(layer)
    cv2.addWeighted(layer, alpha, frame, 1 - alpha, 0, dst=frame)


# --------------------------------------------------------------------------------------
# Piezas
# --------------------------------------------------------------------------------------


def pill(
    frame,
    xy,
    label: str,
    sc: Scale,
    *,
    chosen: bool = False,
    anchor: str = "lb",
    role: str = "strong",
    size: int | None = None,
    alpha: float = 1.0,
    tabular: bool = True,
):
    """Etiqueta tipo píldora. Blanca con tinta; el elegido en naranja con tinta (nunca texto
    blanco sobre naranja). anchor como en text(), sobre la píldora completa. Devuelve su caja."""
    px = size or (sc.px(22) if role == "strong" else sc.size(role))
    tw, th_ = measure(label, sc, role, px, tabular)
    padx, pady = sc.px(14), sc.px(10)
    w, h = tw + 2 * padx, th_ + 2 * pady
    x, y = xy
    x -= {"l": 0, "m": w / 2, "r": w}[anchor[0]]
    y -= {"t": 0, "m": h / 2, "b": h}[anchor[1]]
    x, y = round(x), round(y)
    rounded_rect(
        frame,
        (x, y, w, h),
        sc,
        color="orange" if chosen else "surface",
        alpha=alpha * (1.0 if chosen else 0.94),
        radius=h / 2 / sc.k,
    )
    text(
        frame,
        (x + w / 2, y + h / 2),
        label,
        sc,
        role=role,
        size=px,
        color="ink",
        anchor="mm",
        alpha=alpha,
        tabular=tabular,
    )
    return x, y, x + w, y + h


def corners(
    frame, bbox, sc: Scale, *, chosen: bool = False, alpha: float = 1.0, frac: float = 0.22
):
    """Caja como cuatro esquinas finas (no un rectángulo cerrado): tapa menos al corredor.
    Blanco al 80 %; el elegido en naranja, más grueso y opaco."""
    x1, y1, x2, y2 = map(int, bbox)
    L = int(max(sc.px(8), min(x2 - x1, y2 - y1) * frac))
    t = sc.px(3 if chosen else 2)
    col = ORANGE if chosen else WHITE
    a = alpha * (1.0 if chosen else BOX_ALPHA)

    def draw(img):
        for cx, cy, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
            pts = np.array([(cx + dx * L, cy), (cx, cy), (cx, cy + dy * L)], np.int32)
            cv2.polylines(img, [pts], False, col, t, cv2.LINE_AA)

    _over(frame, draw, a)


def trail(
    frame, pts, sc: Scale, *, chosen: bool = False, alpha: float = 1.0, fade_tail: bool = True
):
    """Estela de los pies. Elegido: naranja 4 px con uniones redondeadas. Resto: blanco 50 %, 2 px.
    Con fade_tail la cola (lo más antiguo) se desvanece."""
    pts = np.asarray(pts, np.float32)
    if len(pts) < 2:
        return
    t = sc.px(4 if chosen else 2)
    col = ORANGE if chosen else WHITE
    base = alpha * (1.0 if chosen else TRAIL_ALPHA)
    chunks = 4 if fade_tail and len(pts) >= 8 else 1
    edges = np.linspace(0, len(pts) - 1, chunks + 1).astype(int)
    for k in range(chunks):
        seg = np.int32(np.round(pts[edges[k] : edges[k + 1] + 1]))
        a = base * (k + 1) / chunks

        def draw(img, seg=seg):
            cv2.polylines(img, [seg], False, col, t, cv2.LINE_AA)
            if chosen:  # uniones redondeadas
                for p in seg:
                    cv2.circle(img, tuple(int(v) for v in p), t // 2, col, -1, cv2.LINE_AA)

        _over(frame, draw, a)


def dot(frame, xy, sc: Scale, *, chosen: bool = False, alpha: float = 1.0, r: float = 5):
    """Punto de apoyo (pie) del corredor."""
    rr = sc.px(r + (1 if chosen else 0))
    c = tuple(int(v) for v in xy)

    def draw(img):
        cv2.circle(img, c, rr, ORANGE if chosen else WHITE, -1, cv2.LINE_AA)

    _over(frame, draw, alpha)


# --------------------------------------------------------------------------------------
# Óvalo cenital (como la vista de la app)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Track:
    """Pista estándar mínima (misma convención que trazada.geometry: s = metros desde la meta,
    sentido antihorario, d = distancia al bordillo). Se usa si no se pasa la de Daniel."""

    radius: float = 36.5
    straight: float = 84.39
    lane_width: float = 1.22
    lanes: int = 8

    @property
    def curve_len(self):
        return math.pi * (self.radius + 0.30)

    @property
    def lap(self):
        return 2 * self.straight + 2 * self.curve_len

    def track_to_world(self, s, d):
        s, d = np.broadcast_arrays(np.mod(np.asarray(s, float), self.lap), np.asarray(d, float))
        s, d = np.atleast_1d(s), np.atleast_1d(d)
        h, c, l, R, Rm = (
            self.straight / 2,
            self.curve_len,
            self.straight,
            self.radius,
            self.radius + 0.30,
        )
        x, y = np.empty_like(s), np.empty_like(s)
        m1, mb = s < c, (s >= c) & (s < c + l)
        m2, mh = (s >= c + l) & (s < 2 * c + l), s >= 2 * c + l
        th = s[m1] / Rm - math.pi / 2
        x[m1], y[m1] = h + (R + d[m1]) * np.cos(th), (R + d[m1]) * np.sin(th)
        x[mb], y[mb] = h - (s[mb] - c), R + d[mb]
        th = (s[m2] - c - l) / Rm + math.pi / 2
        x[m2], y[m2] = -h + (R + d[m2]) * np.cos(th), (R + d[m2]) * np.sin(th)
        x[mh], y[mh] = -h + (s[mh] - 2 * c - l), -(R + d[mh])
        return x, y


STANDARD_TRACK = _Track()


def default_zone_edges(track=STANDARD_TRACK) -> np.ndarray:
    """Las 6 zonas de trazada.zones: curvas partidas en el vértice + las dos rectas."""
    c, l = track.curve_len, track.straight
    return np.array([0, c / 2, c, c + l, c + l + c / 2, 2 * c + l, track.lap])


def oval(
    frame,
    rect,
    sc: Scale,
    *,
    zone: int | None = None,
    s_est: float | None = None,
    s_sd: float | None = None,
    runners_s: list | None = None,
    chosen_s: float | None = None,
    track=None,
    zone_edges=None,
    glass: bool = True,
    band: float = 0.5,
):
    """Óvalo cenital dentro de rect=(x, y, w, h).

    - Carriles grises alternados (#E8E8ED / #DEDEE3) con líneas blancas.
    - Zona actual (1..6) en tinta sobre el carril exterior.
    - Incertidumbre de la estimación como arco naranja suave (#FFD8C4) y punto naranja.
    - runners_s: posiciones s de otros corredores (puntos grises); chosen_s: el elegido (naranja).
    `track` acepta trazada.geometry.STANDARD de Daniel (cualquier objeto con track_to_world, lanes,
    lane_width, curve_len, straight, lap).
    `band`: ancho visual de la pista como fracción del radio. La pista real (8 × 1,22 m) se
    vería como un hilo; como en la app, se exagera para que los carriles se lean."""
    T0 = track or STANDARD_TRACK
    edges = zone_edges if zone_edges is not None else default_zone_edges(T0)
    T = replace(T0, lane_width=band * T0.radius / T0.lanes)
    x, y, w, h = map(int, rect)
    if glass:
        glass_panel(frame, rect, sc)
    pad = sc.px(28)
    D = T.lanes * T.lane_width
    zg, zw = 0.12 * D, 0.30 * D  # separación y grosor de la franja de zona
    span_x = T.straight + 2 * (T.radius + D + zg + zw)
    span_y = 2 * (T.radius + D + zg + zw)
    k = min((w - 2 * pad) / span_x, (h - 2 * pad) / span_y)
    cx, cy = x + w / 2, y + h / 2

    def P(s, d):
        shape = np.broadcast(np.asarray(s), np.asarray(d)).shape
        X, Y = T.track_to_world(np.asarray(s, float), np.asarray(d, float))
        out = np.stack([cx + np.asarray(X, float) * k, cy - np.asarray(Y, float) * k], -1)
        return out.reshape(shape + (2,))

    s = np.linspace(0, T.lap, 360)
    ss = 4  # supermuestreo para bordes suaves
    lay = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)

    def poly(s_arr, d0, d1):
        pts = np.vstack([P(s_arr, d0), P(s_arr[::-1], d1)])
        return [((px - x) * ss, (py - y) * ss) for px, py in pts]

    # carriles alternados
    for ln in range(T.lanes):
        dr.polygon(
            poly(s, ln * T.lane_width, (ln + 1) * T.lane_width),
            fill=rgb("lane_a" if ln % 2 == 0 else "lane_b") + (255,),
        )
    # líneas blancas: todas si el carril mide >= 5 px; si el óvalo es chico, solo bordes
    # y cada 2 carriles, para que no se convierta en una mancha blanca
    lane_px = T.lane_width * k
    step = 1 if lane_px >= 5 else 2
    for ln in range(0, T.lanes + 1, step):
        line = [((px - x) * ss, (py - y) * ss) for px, py in P(s, ln * T.lane_width)]
        dr.line(line + line[:1], fill=(255, 255, 255, 255), width=max(ss, int(sc.k * ss)))
    # zona actual en tinta (franja exterior)
    if zone:
        sz = np.linspace(edges[zone - 1], edges[zone], 60)
        dr.polygon(poly(sz, D + zg, D + zg + zw), fill=rgb("ink") + (255,))
    # incertidumbre (± desviación): tramo naranja suave sobre la pista
    if s_est is not None and s_sd is not None:
        sd = max(s_sd, 1.0)
        sa = np.linspace(s_est - sd, s_est + sd, 40)
        dr.polygon(poly(sa, -0.2, D + 0.2), fill=rgb("cost") + (255,))
    lay_small = lay.resize((w, h), Image.LANCZOS)
    arr = np.asarray(lay_small, np.float32)
    a = arr[..., 3:] / 255.0
    roi = frame[y : y + h, x : x + w].astype(np.float32)
    frame[y : y + h, x : x + w] = (roi * (1 - a) + arr[..., [2, 1, 0]] * a).astype(np.uint8)

    # meta
    a_, b_ = np.int32(np.round(P(0.0, np.array([0.0, D]))))
    cv2.line(frame, tuple(a_), tuple(b_), INK, sc.px(2), cv2.LINE_AA)
    # corredores
    for rs in runners_s or []:
        q = np.int32(np.round(P(rs, D / 2)))
        cv2.circle(frame, tuple(q), sc.px(5), OTHER, -1, cv2.LINE_AA)
    mark = chosen_s if chosen_s is not None else s_est
    if mark is not None:
        q = np.int32(np.round(P(mark, D / 2)))
        cv2.circle(frame, tuple(q), sc.px(6), WHITE, -1, cv2.LINE_AA)
        cv2.circle(frame, tuple(q), sc.px(4.5), ORANGE, -1, cv2.LINE_AA)
    return x, y, w, h


# --------------------------------------------------------------------------------------
# Tiempo: fundidos y suavizado causal
# --------------------------------------------------------------------------------------


def fade(t: float, t_in: float, t_out: float | None = None, dur: float = 0.2) -> float:
    """Opacidad 0..1 para que un elemento aparezca/desaparezca en `dur` s (200 ms), sin saltos."""
    a = min(1.0, max(0.0, (t - t_in) / dur))
    if t_out is not None:
        a = min(a, max(0.0, (t_out - t) / dur))
    return a


class Smoother:
    """Suavizado causal (solo usa el pasado, sirve en vivo) por id: media móvil exponencial
    con constante de tiempo `tau` s. Quita el temblor de cajas y cifras sin adivinar el futuro.

        sm = Smoother(tau=0.15)
        bbox = sm(tid, bbox, t)
    """

    def __init__(self, tau: float = 0.15):
        self.tau, self.state = tau, {}

    def __call__(self, key, value, t: float):
        v = np.asarray(value, np.float64)
        prev = self.state.get(key)
        if prev is None or t - prev[1] > 1.0 or prev[0].shape != v.shape:
            out = v
        else:
            a = 1.0 - math.exp(-max(t - prev[1], 1e-3) / self.tau)
            out = prev[0] + a * (v - prev[0])
        self.state[key] = (out, t)
        return out


def safe_rect(frame, side: float = 0.04, top: float = 0.08, bottom: float = 0.22):
    """Zona segura (x, y, w, h) para nuestros paneles. Las transmisiones ponen el logo y el
    nombre del evento arriba (~8 %) y el reloj de carrera, zócalos y ticker abajo (~20 %):
    ahí no dibujamos paneles. Ajusta los márgenes si un video trae gráficos en otro lugar."""
    H, W = frame.shape[:2]
    x0, y0 = int(W * side), int(H * top)
    return x0, y0, W - 2 * x0, int(H * (1 - bottom)) - y0


def fmt_num(v: float, dec: int = 1, unit: str = "", sign: bool = False) -> str:
    """Cifra a la chilena: punto de miles, coma decimal, espacio antes de la unidad.
    fmt_num(3.2, 1, 'm', True) -> '+3,2 m' · fmt_num(1188, 0, 'm') -> '1.188 m'."""
    s = f"{v:+,.{dec}f}" if sign else f"{v:,.{dec}f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} {unit}".strip()
