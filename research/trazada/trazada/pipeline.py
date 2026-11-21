"""Del frame a la posición de cada corredor en metros.

frame -> YOLO (personas) -> tracker (ID estable) -> punto de apoyo en píxeles
      -> homografía -> (x, y) m -> (s, d) de pista -> filtro -> RunnerState
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .calibration import Calibration
from .filters import RunnerFilter
from .geometry import STANDARD, Track

ANKLES = (15, 16)  # índices COCO de tobillo izq/der en modelos de pose
TRACKER_DIR = Path(__file__).parent / "trackers"


@dataclass
class RunnerState:
    id: int
    t: float
    px: tuple[float, float]       # punto de apoyo en la imagen
    bbox: tuple[float, float, float, float]
    conf: float
    x: float                      # metros, mundo
    y: float
    s: float                      # progreso en la pista (m)
    d: float                      # distancia al bordillo (m)
    lane: int
    segment: str
    speed: float                  # m/s a lo largo de la pista
    extra: float                  # metros de más vs. ir por la cuerda (desde que se le ve)
    rank: int = 0                 # orden entre los corredores visibles
    foot_src: str = "bbox"        # "ankles" si salió de keypoints

    def to_json(self) -> dict:
        j = asdict(self)
        for k in ("x", "y", "s", "d", "speed", "extra", "conf"):
            j[k] = round(j[k], 3)
        j["px"] = [round(v, 1) for v in self.px]
        j["bbox"] = [round(v, 1) for v in self.bbox]
        return j


# ------------------------------------------------------------------ fuente de video
class VideoSource:
    """Lee de archivo, cámara (índice) o stream (rtsp/http).

    En vivo, un hilo lee continuamente y entrega solo el frame más reciente: si el
    modelo va más lento que la cámara se saltan frames en vez de acumular retraso.
    En archivos se procesan todos los frames y el tiempo sale del fps del video.
    """

    def __init__(self, src: str):
        self.live = src.isdigit() or "://" in src
        self.cap = cv2.VideoCapture(int(src) if src.isdigit() else src)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la fuente de video: {src}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.idx = -1
        self._frame, self._t, self._new = None, 0.0, threading.Event()
        self._stop = False
        if self.live:
            threading.Thread(target=self._grab, daemon=True).start()

    def _grab(self):
        while not self._stop:
            ok, f = self.cap.read()
            if not ok:
                self._stop = True
                self._new.set()
                break
            self._frame, self._t = f, time.monotonic()
            self._new.set()

    def read(self):
        """-> (frame, t_segundos) o (None, None) al terminar."""
        if self.live:
            self._new.wait()
            self._new.clear()
            if self._stop and self._frame is None:
                return None, None
            f, self._frame = self._frame, None
            if f is None:
                return None, None
            self.idx += 1
            return f, self._t
        ok, f = self.cap.read()
        if not ok:
            return None, None
        self.idx += 1
        return f, self.idx / self.fps

    def release(self):
        self._stop = True
        self.cap.release()


# ------------------------------------------------------------------ localizador
class RunnerLocator:
    def __init__(self, calib: Calibration, model: str = "yolo26n.pt", tracker: str = "bytetrack_runners.yaml",
                 imgsz: int = 960, conf: float = 0.25, device: str | None = None,
                 track: Track = STANDARD, margin_m: float = 1.0, forget_s: float = 3.0,
                 calib_provider=None):
        from ultralytics import YOLO  # import diferido: los tests de geometría no lo necesitan

        self.model = YOLO(model)
        self.is_pose = getattr(self.model, "task", "") == "pose"
        tp = TRACKER_DIR / tracker
        self.tracker = str(tp) if tp.exists() else tracker
        self.calib, self.track = calib, track
        self.imgsz, self.conf = imgsz, conf
        self.device = device or _best_device()
        self.d_range = (-margin_m, track.lanes * track.lane_width + margin_m)
        self.forget_s = forget_s
        # cámara que se mueve: función (frame, cajas) -> Calibration, llamada en cada frame
        self.calib_provider = calib_provider
        self.filters: dict[int, RunnerFilter] = {}   # por ID estable de corredor
        self.alias: dict[int, int] = {}               # ID del tracker -> ID estable
        self._next_id = 0
        self.max_dd, self.max_ds = 0.6, 2.0   # metros: tolerancia antes de declarar un swap
        self._calib_checked = False

    def reset(self):
        self.filters.clear()
        self.alias.clear()
        if getattr(self.model, "predictor", None) is not None:
            for tr in getattr(self.model.predictor, "trackers", []) or []:
                tr.reset()

    def process(self, frame: np.ndarray, t: float) -> list[RunnerState]:
        if not self._calib_checked:
            h, w = frame.shape[:2]
            if tuple(self.calib.image_size) != (w, h):
                self.calib = self.calib.scaled_to(w, h)
            self._calib_checked = True

        res = self.model.track(frame, persist=True, tracker=self.tracker, classes=[0], imgsz=self.imgsz,
                               conf=self.conf, device=self.device, verbose=False)[0]
        b = res.boxes
        if self.calib_provider is not None:
            all_boxes = b.xyxy.cpu().numpy() if b is not None and len(b) else np.zeros((0, 4))
            self.calib = self.calib_provider(frame, all_boxes)
        if b is None or b.id is None or len(b) == 0:
            self._forget(t)
            return []

        xyxy = b.xyxy.cpu().numpy()
        ids = b.id.int().cpu().numpy()
        confs = b.conf.cpu().numpy()
        feet = np.stack([(xyxy[:, 0] + xyxy[:, 2]) / 2, xyxy[:, 3]], axis=1)
        src = np.array(["bbox"] * len(ids), dtype=object)

        if self.is_pose and res.keypoints is not None and res.keypoints.conf is not None:
            kxy = res.keypoints.xy.cpu().numpy()[:, ANKLES, :]
            kc = res.keypoints.conf.cpu().numpy()[:, ANKLES]
            for i in range(len(ids)):
                ok = kc[i] > 0.5
                if ok.any():
                    # el pie más bajo en la imagen es el que está apoyado (o más cerca de estarlo)
                    feet[i] = kxy[i][ok][np.argmax(kxy[i][ok][:, 1])]
                    src[i] = "ankles"

        world = self.calib.img_to_world(feet)
        s_arr, d_arr = self.track.world_to_track(world[:, 0], world[:, 1])
        s_arr, d_arr = np.atleast_1d(s_arr), np.atleast_1d(d_arr)

        keep = [i for i in range(len(ids)) if self.d_range[0] <= d_arr[i] <= self.d_range[1]]  # fuera: público, pasto
        rids = self._stitch([int(ids[i]) for i in keep], s_arr[keep], d_arr[keep], t)

        out: list[RunnerState] = []
        for i, rid in zip(keep, rids):
            f = self.filters.setdefault(rid, RunnerFilter(self.track))
            s, d, v = f.update(float(s_arr[i]), float(d_arr[i]), t)
            x, y = self.track.track_to_world(s, d)
            out.append(RunnerState(
                id=rid, t=t, px=(float(feet[i, 0]), float(feet[i, 1])),
                bbox=tuple(float(v_) for v_ in xyxy[i]), conf=float(confs[i]),
                x=x, y=y, s=s, d=d, lane=self.track.lane_of(d), segment=self.track.segment(s),
                speed=v, extra=f.extra, foot_src=str(src[i])))

        # orden: el que va adelante es 1. Se mide relativo a un ancla con ds_wrap para que el
        # salto 400 -> 0 en la meta no desordene (el grupo visible siempre ocupa < 200 m).
        if out:
            anchor = out[0].s
            for k, r in enumerate(sorted(out, key=lambda r: -self.track.ds_wrap(anchor, r.s))):
                r.rank = k + 1
        self._forget(t)
        return out

    def _stitch(self, tids: list[int], s_arr, d_arr, t: float) -> list[int]:
        """ID del tracker -> ID estable del corredor.

        Cuando el tracker pierde a alguien en una oclusión y lo retoma con un ID nuevo, aquí se
        reconecta con el corredor perdido cuya posición predicha en la pista (s + v·Δt, d) cae
        cerca. En metros sobre la pista esto es mucho más fiable que en píxeles: la gente corre
        hacia adelante a velocidad casi constante y cambia de pista despacio.
        """
        # 1) Romper asignaciones físicamente imposibles. En un adelantamiento con oclusión el
        #    tracker a veces "salta" de un corredor al otro (swap). Un salto lateral o hacia
        #    adelante que nadie puede correr delata el error: se suelta el ID y se re-asigna abajo.
        for j, k in enumerate(tids):
            rid = self.alias.get(k)
            f = self.filters.get(rid) if rid is not None else None
            if f is None or f.s.x is None:
                continue
            gap = max(0.0, t - f.last_t)
            ds = self.track.ds_wrap(f.s.x + f.speed * gap, float(s_arr[j]))
            dd = float(d_arr[j]) - f.d.x
            if abs(dd) > self.max_dd + 1.2 * gap or abs(ds) > self.max_ds + 2.0 * gap:
                del self.alias[k]

        # 2) IDs nuevos del tracker -> corredor perdido más cercano a su predicción.
        live = set(tids)
        taken = {self.alias[k] for k in tids if k in self.alias}
        lost = {rid: f for rid, f in self.filters.items()
                if rid not in taken and f.last_t is not None and f.last_t < t
                and not any(self.alias.get(k) == rid for k in live)}
        new = [(j, k) for j, k in enumerate(tids) if k not in self.alias]
        pairs = []
        for j, k in new:
            for rid, f in lost.items():
                gap = t - f.last_t
                ds = self.track.ds_wrap(f.s.x + f.speed * gap, float(s_arr[j]))
                dd = float(d_arr[j]) - f.d.x
                if abs(ds) < 1.5 + 1.0 * gap and abs(dd) < 0.8 + 0.5 * gap:
                    pairs.append((abs(ds) + 2 * abs(dd), j, k, rid))
        used_j, used_r = set(), set()
        for _, j, k, rid in sorted(pairs):
            if j not in used_j and rid not in used_r:
                self.alias[k] = rid
                used_j.add(j); used_r.add(rid)
        for j, k in new:
            if k not in self.alias:
                self._next_id += 1
                self.alias[k] = self._next_id
        return [self.alias[k] for k in tids]

    def _forget(self, t: float):
        for k in [k for k, f in self.filters.items() if f.last_t is not None and t - f.last_t > self.forget_s]:
            del self.filters[k]
        alive = set(self.filters)
        self.alias = {k: v for k, v in self.alias.items() if v in alive}


def _best_device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
