"""Resumen determinista de un clip ya procesado: la única fuente de verdad del relato.

No llama a nadie y no inventa nada: convierte /track + /zones en una hoja de hechos corta
(la que se le manda al modelo) y en las cifras que después se usan para validar el guion.

La regla de oro: lo que no esté aquí, el relato no lo puede decir.
"""

import re
from statistics import median

from app.schemas.tracking import TrackingResult
from app.schemas.zones import ZonesResult

# Cuántos corredores se detallan. Con más, el prompt crece sin aportar: el resto se resume.
MAX_TRACKS_IN_FACTS = 12

CAN_CLAIM = [
    "cuántos corredores se siguen en total",
    "cuántos caben en cuadro a la vez",
    "cuándo aparece o se pierde un corredor de cuadro",
    "qué tramo de pista enfoca la cámara y cuánto lo recorre",
    "cuántos cambios de plano hay",
]

CANNOT_CLAIM = [
    "posiciones o puestos de cada corredor",
    "quién va adelante, quién lidera o quién gana",
    "distancias entre corredores",
    "tiempos de carrera, parciales, récords o marcas",
    "nombres, dorsales, clubes o nacionalidades",
]


def build_facts(tracks: TrackingResult, zones: ZonesResult | None) -> dict:
    """Hoja de hechos que se le entrega al modelo. Todo en unidades del video."""
    on_screen = [len(f.detections) for f in tracks.frames]
    ordered = sorted(tracks.tracks, key=lambda t: t.n_obs, reverse=True)

    facts: dict = {
        "clip": {
            "duration_s": tracks.video.duration_s,
            "fps_out": tracks.video.fps_out,
            "frames": tracks.video.frames,
        },
        "runners": {
            "total": len(tracks.tracks),
            "peak_on_screen": max(on_screen, default=0),
            "median_on_screen": round(median(on_screen), 1) if on_screen else 0,
        },
        "tracks": [
            {
                "id": t.id,
                "in_s": round(t.t_start, 1),
                "out_s": round(t.t_end, 1),
                "observations": t.n_obs,
                "on_track_pct": round(t.on_track * 100),
            }
            for t in ordered[:MAX_TRACKS_IN_FACTS]
        ],
        "can_claim": CAN_CLAIM,
        "cannot_claim": CANNOT_CLAIM,
    }
    if len(ordered) > MAX_TRACKS_IN_FACTS:
        facts["tracks_note"] = (
            f"Se detallan los {MAX_TRACKS_IN_FACTS} corredores que más tiempo estuvieron en cuadro "
            f"de {len(ordered)} en total."
        )
    if zones is not None:
        facts["camera"] = _camera_facts(zones)
    return facts


def _camera_facts(zones: ZonesResult) -> dict:
    """Timeline por zona: qué tramo de pista enfocó la cámara y en qué ventana de tiempo."""
    timeline: list[dict] = []
    for f in zones.frames:
        if timeline and timeline[-1]["zone"] == f.zone:
            timeline[-1]["to_s"] = f.t
            timeline[-1]["s_to_m"] = f.s
        else:
            timeline.append(
                {
                    "from_s": f.t,
                    "to_s": f.t,
                    "zone": f.zone,
                    "zone_name": zones.zone_names.get(f.zone, f"zona {f.zone}"),
                    "s_from_m": f.s,
                    "s_to_m": f.s,
                }
            )

    ss = [f.s for f in zones.frames]
    speeds = [f.v for f in zones.frames if f.v > 0]
    return {
        "timeline": [
            {
                **step,
                "from_s": round(step["from_s"], 1),
                "to_s": round(step["to_s"], 1),
                "s_from_m": round(step["s_from_m"], 0),
                "s_to_m": round(step["s_to_m"], 0),
            }
            for step in timeline
        ],
        "span_m": round(max(ss) - min(ss)) if ss else 0,
        "cuts": len(zones.cuts),
        "pan_speed_mps": round(median(speeds), 1) if speeds else 0,
    }


_DIGIT = re.compile(r"\d+(?:[.,]\d+)?")


def allowed_numbers(facts: dict) -> set[float]:
    """Todo número de la hoja de hechos. El guion no puede usar cifras que no estén acá.

    También cuentan los dígitos que aparecen dentro de un texto: los nombres de zona del
    backend los llevan ("curva 1 salida"), y decir el nombre de la zona es legítimo.
    """
    found: set[float] = set()

    def walk(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            found.add(round(float(value), 1))
        elif isinstance(value, str):
            found.update(float(m.replace(",", ".")) for m in _DIGIT.findall(value))
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(facts)
    return found
