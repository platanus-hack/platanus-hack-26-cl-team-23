// Adaptador: traduce las respuestas del backend (/api/tracking/* y /api/zones/*) al modelo
// interno `Race`, que es lo único que conocen los componentes de dibujo. Es la única
// frontera entre los contratos de la API y la pantalla.

import { CURVE, LAP, MEAS, R, STRAIGHT, type Vec2 } from './geometry'
import type {
  AthleteSample,
  AthleteSummary,
  AthletesResult,
  Race,
  RaceFrame,
  RunnerInfo,
  RunnerSample,
  TrackingResult,
  ZonesResult,
} from './types'

const PALETTE = ['#e5484d', '#f5c542', '#9b6cf2', '#4c8dff', '#3dd68c', '#ff8bd1', '#5fd4f4', '#c7d36f']

export type RaceMeta = {
  title: string
  note?: string
  videoUrl?: string
}

export function buildRace(
  tracks: TrackingResult,
  zones: ZonesResult | undefined,
  athletes: AthletesResult | undefined,
  meta: RaceMeta,
): Race {
  // Los JSON se unen por el número de cuadro: es la posición en la lista que se envió.
  const zoneByFrame = new Map(zones?.frames.map((z) => [z.frame, z]))
  const athletesByFrame = new Map(athletes?.frames.map((a) => [a.frame, a]))

  const frames: RaceFrame[] = tracks.frames.map((f) => {
    const z = zoneByFrame.get(f.frame)
    const states: AthleteSample[] | undefined = athletesByFrame.get(f.frame)?.athletes.map((a) => ({
      id: a.id,
      trackId: a.track_id,
      rank: a.rank,
      x: a.x,
      s: a.s,
      d: a.d,
      lane: a.lane,
      v: a.v,
      u: a.u,
      visible: a.visible,
      sigmaX: a.sigma_x,
    }))
    // Qué atleta es cada caja: lo dice track_id. Las cajas sin atleta (planos sin medición)
    // no se pueden elegir.
    const athleteOfTrack = new Map(states?.flatMap((a) => (a.trackId === null ? [] : [[a.trackId, a.id] as const])))
    const runners: RunnerSample[] = f.detections.map((det) => ({
      id: det.id,
      rid: athletes ? athleteOfTrack.get(det.id) : det.id,
      bbox: det.bbox as [number, number, number, number],
      footPx: det.foot_px as Vec2,
      conf: det.conf,
    }))
    return { t: f.t, runners, zone: z?.zone, focusS: z?.s, focusV: z?.v, cut: z?.cut, athletes: states }
  })

  const runners = athletes ? athleteRunners(frames, tracks) : trackRunners(tracks)

  return {
    title: meta.title,
    note: meta.note,
    video: {
      width: tracks.video.width,
      height: tracks.video.height,
      duration: tracks.video.duration_s,
      url: meta.videoUrl,
    },
    pipeline: { detector: tracks.pipeline.detector, tracker: tracks.pipeline.tracker },
    runners,
    frames,
    camera: zones && readCamera(zones),
    hasAthletes: athletes !== undefined,
    // Con atletas, el que mejor se midió; si no, el que se siguió por más tiempo.
    defaultId: [...runners].sort((a, b) => b.nObs - a.nObs)[0]?.id,
    raw: { tracks, zones, athletes },
  }
}

/** Sin atletas: un corredor por cada track del seguimiento. */
function trackRunners(tracks: TrackingResult): RunnerInfo[] {
  return tracks.tracks.map((t, i) => ({
    id: t.id,
    label: `#${t.id}`,
    color: PALETTE[i % PALETTE.length],
    tStart: t.t_start,
    tEnd: t.t_end,
    nObs: t.n_obs,
    onTrack: t.on_track,
  }))
}

/** Con atletas: un corredor por atleta, con id estable aunque la cámara corte de plano. */
function athleteRunners(frames: RaceFrame[], tracks: TrackingResult): RunnerInfo[] {
  const onTrackOf = new Map(tracks.tracks.map((t) => [t.id, t.on_track]))
  type Acc = { samples: { t: number; a: AthleteSample }[]; onTrack: number[] }
  const byId = new Map<number, Acc>()
  for (const f of frames) {
    for (const a of f.athletes ?? []) {
      const acc = byId.get(a.id) ?? { samples: [], onTrack: [] }
      byId.set(a.id, acc)
      if (!a.visible) continue
      acc.samples.push({ t: f.t, a })
      const ot = a.trackId === null ? undefined : onTrackOf.get(a.trackId)
      if (ot !== undefined) acc.onTrack.push(ot)
    }
  }
  return [...byId.entries()]
    .filter(([, acc]) => acc.samples.length > 0)
    .sort(([a], [b]) => a - b)
    .map(([id, acc], i) => ({
      id,
      label: `#${id}`,
      color: PALETTE[i % PALETTE.length],
      tStart: acc.samples[0].t,
      tEnd: acc.samples[acc.samples.length - 1].t,
      nObs: acc.samples.length,
      onTrack: acc.onTrack.length ? acc.onTrack.reduce((s, v) => s + v, 0) / acc.onTrack.length : 1,
      summary: summarize(acc.samples),
    }))
}

/** ¿Está esta posición (metros desde la meta) dentro de una curva? */
function inCurve(s: number): boolean {
  const u = ((s % LAP) + LAP) % LAP
  return u < CURVE || (u >= CURVE + STRAIGHT && u < 2 * CURVE + STRAIGHT)
}

/**
 * Resumen de un corredor. Los metros extra: en una curva, quien corre a `d` m del bordillo
 * recorre (R + d) / (R + MEAS) veces lo que la línea de medición de la calle 1; la diferencia,
 * sumada paso a paso, es lo que le cuesta ir por fuera. Es una estimación: `d` tiene ~0,3 m de error.
 */
function summarize(samples: { t: number; a: AthleteSample }[]): AthleteSummary {
  let extra = 0
  let meters = 0
  let vSum = 0
  let maxV = 0
  for (let i = 0; i < samples.length; i++) {
    const { a } = samples[i]
    vSum += a.v
    maxV = Math.max(maxV, a.v)
    if (i === 0) continue
    const prev = samples[i - 1]
    const dx = a.x - prev.a.x
    // Solo pasos entre cuadros seguidos: un salto grande es un corte de plano, no una carrera.
    if (samples[i].t - prev.t > 0.35 || dx <= 0 || dx > 3) continue
    meters += dx
    if (inCurve(a.s)) extra += dx * (Math.max(MEAS, a.d) - MEAS) / (R + MEAS)
  }
  return {
    avgV: vSum / samples.length,
    maxV,
    meters,
    extraM: extra,
    startRank: samples[0].a.rank,
    endRank: samples[samples.length - 1].a.rank,
  }
}

/** Lo que la cámara recorrió de la pista, para la vista cenital. */
function readCamera(zones: ZonesResult): Race['camera'] {
  const ss = zones.frames.map((f) => f.s)
  return {
    names: Object.fromEntries(Object.entries(zones.zone_names).map(([k, v]) => [Number(k), v])),
    span: [Math.min(...ss), Math.max(...ss)],
    cuts: zones.cuts,
  }
}

/**
 * Corredores a mostrar en el cuadro fi. El detector a veces pierde a alguien por un
 * cuadro y lo recupera al siguiente: eso hace parpadear etiquetas y filas. Para evitarlo
 * mantenemos visible la última detección de cada corredor durante `hold` segundos.
 * Sigue siendo causal: solo usa cuadros pasados.
 */
export function visibleAt(frames: RaceFrame[], fi: number, hold = 0.5): (RunnerSample & { stale: boolean })[] {
  const frame = frames[fi]
  if (!frame) return []
  const out = new Map<number, RunnerSample & { stale: boolean }>()
  for (const r of frame.runners) out.set(r.id, { ...r, stale: false })
  for (let i = fi - 1; i >= 0 && frame.t - frames[i].t <= hold; i--)
    for (const r of frames[i].runners) if (!out.has(r.id)) out.set(r.id, { ...r, stale: true })
  return [...out.values()]
}

/** El cuadro vigente en el tiempo t: el último con t <= ahora (nunca miramos al futuro). */
export function frameAt(frames: RaceFrame[], t: number): number {
  let lo = 0
  let hi = frames.length - 1
  if (hi < 0 || t < frames[0].t) return 0
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (frames[mid].t <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}
