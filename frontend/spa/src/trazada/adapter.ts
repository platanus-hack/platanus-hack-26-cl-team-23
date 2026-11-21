// Adaptador: traduce lo que entregan Andrés (seguimiento) y Daniel (geometría)
// al modelo interno `Race`, que es lo único que conocen los componentes de dibujo.
//
// Para enchufar los datos reales basta con cambiar `loadRace()`:
//   const tracks = await fetch('/api/.../tracks.json').then(r => r.json())
//   const geometry = await fetch('/api/.../geometry.json').then(r => r.json())
//   return buildRace({ tracks, geometry, videoUrl: '/api/.../video.mp4', title: '...' })

import type { Vec2 } from './geometry'
import type {
  GeometryJson,
  Race,
  RaceFrame,
  RunnerInfo,
  RunnerResult,
  RunnerSample,
  TracksJson,
} from './types'

const PALETTE = ['#e5484d', '#f5c542', '#9b6cf2', '#4c8dff', '#3dd68c', '#ff8bd1', '#5fd4f4', '#c7d36f']

export type RaceMeta = {
  title: string
  note?: string
  isMock?: boolean
  videoUrl?: string
  cameraSpan?: [number, number]
  /** Datos opcionales por corredor (dorsal, color, quién es el protagonista). */
  runners?: Partial<Record<number, Partial<Omit<RunnerInfo, 'id'>>>>
}

export function buildRace(tracks: TracksJson, geometry: GeometryJson | undefined, meta: RaceMeta): Race {
  // Une ambos archivos por número de cuadro.
  const geoByFrame = new Map(geometry?.frames.map((g) => [g.frame, g]))

  const frames: RaceFrame[] = tracks.frames.map((f) => {
    const g = geoByFrame.get(f.frame)
    const geoById = new Map(g?.runners.map((r) => [r.id, r]))
    const runners: RunnerSample[] = f.detections.map((det) => {
      const geo = geoById.get(det.id)
      return {
        id: det.id,
        bbox: det.bbox,
        footPx: det.foot_px as Vec2,
        s: geo?.s,
        d: geo?.d,
        extraM: geo?.extra_m,
      }
    })
    return { t: f.t, zone: g?.zone, worldToImage: g?.H, runners }
  })

  const results = geometry?.summary
    ? geometry.summary.map((r) => ({ id: r.id, startRank: r.start_rank, endRank: r.end_rank, extraM: r.extra_m }))
    : computeResults(frames)

  const runners: RunnerInfo[] = tracks.tracks.map((t, i) => ({
    id: t.id,
    label: `#${t.id}`,
    color: PALETTE[i % PALETTE.length],
    tStart: t.t_start,
    tEnd: t.t_end,
    ...meta.runners?.[t.id],
  }))

  // Si nadie dijo quién es el protagonista, elegimos al que más puestos ganó.
  const heroId =
    runners.find((r) => r.hero)?.id ??
    [...results].sort((a, b) => b.startRank - b.endRank - (a.startRank - a.endRank))[0]?.id ??
    // sin geometría no hay puestos: elegimos al que se siguió por más tiempo
    [...tracks.tracks].sort((a, b) => b.n_obs - a.n_obs)[0]?.id

  return {
    title: meta.title,
    note: meta.note,
    isMock: meta.isMock ?? false,
    video: { width: tracks.video.width, height: tracks.video.height, duration: tracks.video.duration_s, url: meta.videoUrl },
    runners: runners.map((r) => ({ ...r, hero: r.id === heroId })),
    frames,
    cameraSpan: meta.cameraSpan,
    results,
    heroId,
  }
}

/** Puesto al inicio y al final según s, y metros extra al final. Solo si Daniel no manda el resumen. */
export function computeResults(frames: RaceFrame[]): RunnerResult[] {
  const first = new Map<number, RunnerSample>()
  const last = new Map<number, RunnerSample>()
  for (const f of frames)
    for (const r of f.runners) {
      if (r.s === undefined) continue
      if (!first.has(r.id)) first.set(r.id, r)
      last.set(r.id, r)
    }
  const rankBy = (m: Map<number, RunnerSample>) =>
    new Map([...m.values()].sort((a, b) => b.s! - a.s!).map((r, i) => [r.id, i + 1]))
  const start = rankBy(first)
  const end = rankBy(last)
  return [...last.keys()].map((id) => ({
    id,
    startRank: start.get(id)!,
    endRank: end.get(id)!,
    extraM: last.get(id)!.extraM ?? 0,
  }))
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

// ---------------------------------------------------------------------
// Punto único de entrada de datos para la pantalla.
//   'real'       → video NCCA + seguimiento real de Andrés (falta la geometría de Daniel)
//   'simulacion' → carrera inventada con todos los datos, para explicar la idea
// ---------------------------------------------------------------------
export type RaceSource = 'real' | 'simulacion'

export async function loadRace(source: RaceSource = 'real'): Promise<Race> {
  if (source === 'real') {
    const real = await import('./data/realNcca')
    const { tracks, geometry, meta } = await real.load()
    return buildRace(tracks, geometry, meta)
  }
  const mock = await import('./data/mockRace')
  return buildRace(mock.tracks, mock.geometry, mock.meta)
}
