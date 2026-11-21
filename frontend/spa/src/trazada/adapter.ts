// Adaptador: traduce las respuestas del backend (/api/tracking/* y /api/zones/*) al modelo
// interno `Race`, que es lo único que conocen los componentes de dibujo. Es la única
// frontera entre los contratos de la API y la pantalla.

import type { Vec2 } from './geometry'
import type { Race, RaceFrame, RunnerInfo, RunnerSample, TrackingResult, ZonesResult } from './types'

const PALETTE = ['#e5484d', '#f5c542', '#9b6cf2', '#4c8dff', '#3dd68c', '#ff8bd1', '#5fd4f4', '#c7d36f']

export type RaceMeta = {
  title: string
  note?: string
  videoUrl?: string
}

export function buildRace(tracks: TrackingResult, zones: ZonesResult | undefined, meta: RaceMeta): Race {
  // Ambos JSON se unen por el número de cuadro: es la posición en la lista que se envió.
  const zoneByFrame = new Map(zones?.frames.map((z) => [z.frame, z]))

  const frames: RaceFrame[] = tracks.frames.map((f) => {
    const z = zoneByFrame.get(f.frame)
    const runners: RunnerSample[] = f.detections.map((det) => ({
      id: det.id,
      bbox: det.bbox as [number, number, number, number],
      footPx: det.foot_px as Vec2,
      conf: det.conf,
    }))
    return { t: f.t, runners, zone: z?.zone, focusS: z?.s, focusV: z?.v, cut: z?.cut }
  })

  const runners: RunnerInfo[] = tracks.tracks.map((t, i) => ({
    id: t.id,
    label: `#${t.id}`,
    color: PALETTE[i % PALETTE.length],
    tStart: t.t_start,
    tEnd: t.t_end,
    nObs: t.n_obs,
    onTrack: t.on_track,
  }))

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
    // Sin metros no hay puestos: elegimos al que se siguió por más tiempo.
    defaultId: [...runners].sort((a, b) => b.nObs - a.nObs)[0]?.id,
    raw: { tracks, zones },
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
