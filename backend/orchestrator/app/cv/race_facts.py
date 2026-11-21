"""Resumen determinista de un clip ya procesado: la única fuente de verdad del relato.

No llama a nadie y no inventa nada: convierte /track + /zones en una hoja de hechos corta
(la que se le manda al modelo) y en las cifras que después se usan para validar el guion.

La regla de oro: lo que no esté aquí, el relato no lo puede decir.
"""

import itertools
import re
from collections import Counter
from statistics import median

from app.cv.zones.track import STANDARD
from app.schemas.athletes import AthletesResult, AthleteState
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

CAN_CLAIM_ATHLETES = [
    "el orden entre los atletas medidos (rank) y quién va primero del grupo medido",
    "los adelantamientos que aparecen en athletes.passes, con su segundo",
    "la velocidad de cada uno en km/h (media y máxima) y el ritmo del grupo",
    "por qué calle corre cada uno y cuántos metros extra gasta por ir por fuera",
    "cuántos metros separan al primero del último medido",
    "cuántos corredores caben en cuadro y en qué tramo de pista van",
]

CANNOT_CLAIM_ATHLETES = [
    "quién gana la carrera, tiempos, parciales, récords o marcas",
    "el puesto real en la carrera completa: solo se mide al grupo que se ve",
    "la distancia exacta entre dos corredores concretos (solo la del primero al último)",
    "nombres, dorsales, clubes o nacionalidades",
]

CANNOT_CLAIM = [
    "posiciones o puestos de cada corredor",
    "quién va adelante, quién lidera o quién gana",
    "distancias entre corredores",
    "tiempos de carrera, parciales, récords o marcas",
    "nombres, dorsales, clubes o nacionalidades",
]


def build_facts(
    tracks: TrackingResult, zones: ZonesResult | None, athletes: AthletesResult | None = None
) -> dict:
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
    summary = _athlete_facts(athletes, zones) if athletes is not None else None
    if summary is not None:
        # Con atletas medidos, los corredores son ellos (sus ids son los que se ven en pantalla)
        # y el relato puede hablar de puestos y velocidad.
        facts["athletes"] = summary
        facts["runners"]["total"] = len(summary["runners"])
        facts.pop("tracks")
        facts.pop("tracks_note", None)
        facts["can_claim"] = CAN_CLAIM_ATHLETES
        facts["cannot_claim"] = CANNOT_CLAIM_ATHLETES
    return facts


def runner_ids(facts: dict) -> set[float]:
    """Ids que el relato puede nombrar con '#'."""
    if "athletes" in facts:
        return {float(r["id"]) for r in facts["athletes"]["runners"]}
    return {float(t["id"]) for t in facts["tracks"]}


KMH = 3.6
# Un salto mayor entre cuadros medidos es un corte de plano, no una carrera continua.
MAX_STEP_S = 0.35
# Muestreo del timeline y separación mínima entre dos adelantamientos del mismo par.
TIMELINE_EVERY_S = 2.0
PASS_COOLDOWN_S = 3.0
MAX_PASSES = 8
# Debajo de esto, los metros extra por ir por fuera son ruido de medición: no se informan.
MIN_EXTRA_M = 1.0


def _in_curve(s: float) -> bool:
    lap, c, straight = STANDARD.lap, STANDARD.curve_len, STANDARD.straight
    u = s % lap
    return u < c or c + straight <= u < 2 * c + straight


def _athlete_facts(athletes: AthletesResult, zones: ZonesResult | None) -> dict | None:
    """Puestos, velocidad, calles y adelantamientos, ya resumidos para que el modelo narre sin
    tener que interpretar series de datos."""
    seen: dict[int, list[tuple[float, AthleteState]]] = {}
    for frame in athletes.frames:
        for a in frame.athletes:
            if a.visible:
                seen.setdefault(a.id, []).append((frame.t, a))
    if not seen:
        return None

    track = STANDARD
    runners = []
    for athlete_id, samples in seen.items():
        extra = 0.0
        for (t0, a0), (t1, a1) in itertools.pairwise(samples):
            dx = a1.x - a0.x
            if t1 - t0 > MAX_STEP_S or dx <= 0 or dx > 3:
                continue
            if _in_curve(a1.s):
                extra += (
                    dx
                    * (max(track.meas_offset, a1.d) - track.meas_offset)
                    / (track.radius + track.meas_offset)
                )
        speeds = [a.v for _, a in samples]
        lane = Counter(a.lane for _, a in samples).most_common(1)[0][0]
        runners.append(
            {
                "id": athlete_id,
                "in_s": round(samples[0][0], 1),
                "out_s": round(samples[-1][0], 1),
                "rank_start": samples[0][1].rank,
                "rank_end": samples[-1][1].rank,
                "avg_kmh": round(sum(speeds) / len(speeds) * KMH, 1),
                "max_kmh": round(max(speeds) * KMH, 1),
                "lane": lane,
                "side": "por dentro" if lane == 1 else "por fuera" if lane >= 3 else "en el medio",
                "extra_m": round(extra, 1) if extra >= MIN_EXTRA_M else None,
            }
        )
    runners.sort(key=lambda r: r["out_s"] - r["in_s"], reverse=True)
    runners = runners[:MAX_TRACKS_IN_FACTS]

    timeline: list[dict] = []
    passes: list[dict] = []
    last_pass: dict[tuple[int, int], float] = {}
    paces: list[float] = []
    spreads: list[float] = []
    next_sample = 0.0
    prev_rank: dict[int, int] = {}
    for frame in athletes.frames:
        visible = [a for a in frame.athletes if a.visible]
        if visible:
            mean_v = sum(a.v for a in visible) / len(visible)
            paces.append(mean_v)
            spread = max(a.x for a in visible) - min(a.x for a in visible)
            spreads.append(spread)
            if frame.t >= next_sample:
                next_sample = frame.t + TIMELINE_EVERY_S
                timeline.append(
                    {
                        "t_s": round(frame.t, 1),
                        "leader": min(visible, key=lambda a: a.rank).id,
                        "pace_kmh": round(mean_v * KMH, 1),
                        "spread_m": round(spread, 1),
                        "in_view": len(visible),
                    }
                )
        # Adelantamiento: dos atletas medidos en cuadros seguidos que cambian de orden.
        now = {a.id: a.rank for a in visible}
        for a, b in itertools.permutations(now, 2):
            if (
                a in prev_rank
                and b in prev_rank
                and prev_rank[a] > prev_rank[b]
                and now[a] < now[b]
            ):
                if (
                    frame.t - last_pass.get((a, b), -1e9) >= PASS_COOLDOWN_S
                    and len(passes) < MAX_PASSES
                ):
                    passes.append({"t_s": round(frame.t, 1), "id": a, "passes": b})
                last_pass[(a, b)] = frame.t
        prev_rank = now

    first = timeline[0] if timeline else None
    last = timeline[-1] if timeline else None
    outside = [r for r in runners if r["extra_m"] is not None]
    widest = max(outside, key=lambda r: r["extra_m"]) if outside else None
    return {
        "distance_m": round(zones.distance) if zones is not None else None,
        "field": {
            "measured": len(seen),
            "pace_kmh": round(median(paces) * KMH, 1) if paces else 0,
            "spread_start_m": first["spread_m"] if first else 0,
            "spread_end_m": last["spread_m"] if last else 0,
            "leader_start": first["leader"] if first else None,
            "leader_end": last["leader"] if last else None,
        },
        "runners": runners,
        "timeline": timeline,
        "passes": passes,
        "widest": {"id": widest["id"], "extra_m": widest["extra_m"]} if widest else None,
        "ranks_note": (
            "rank ordena solo a los atletas medidos en el clip (1 = va primero de ese grupo); "
            "no es el puesto de la carrera completa."
        ),
    }


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
