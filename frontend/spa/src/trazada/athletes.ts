// Atletas: posición y velocidad de cada corredor respecto a la cancha.
//
// Se apoya en lo que ya sacamos del video: las cajas con id de /track (Roboflow + ByteTrack)
// y la posición del grupo de /zones. Dos pasos, igual que el resto:
// medición por lote de cuadros CONSECUTIVOS (POST /api/athletes/features, sin estado)
// y un filtro final sobre todo el video (POST /api/athletes/).

import { apiPost, apiUpload } from '../lib/api'
import type { components } from '../types/api.gen'
import type { AthletesResult, TrackingResult, ZonesResult } from './types'

type AthleteFeaturesResponse = components['schemas']['AthleteFeaturesResponse']
type AthleteFrameFeatures = components['schemas']['AthleteFrameFeatures']

export type AthleteOptions = {
  /** Corredores en la serie: el algoritmo nunca inventa más que estos. */
  fieldSize: number
  /** Segundo del video en que suena el disparo (el mismo que usan las zonas). */
  t0: number
}

export const DEFAULT_ATHLETE_OPTIONS: AthleteOptions = { fieldSize: 12, t0: 0 }

/** Cuadros por petición: más chico que el de detección porque cada cuadro viaja otra vez. */
export const ATHLETE_BATCH = 12

type SentFrame = { index: number; t: number; jpeg: Blob }

/** Cajas `[id, x1, y1, x2, y2]` de un lote, en píxeles del video original (salida de /track). */
function boxesOf(tracks: TrackingResult, batch: SentFrame[]): number[][][] {
  return batch.map((f) => (tracks.frames[f.index]?.detections ?? []).map((d) => [d.id, ...d.bbox]))
}

/** Medición de un lote de cuadros consecutivos. */
export function measureAthletes(
  batch: SentFrame[],
  tracks: TrackingResult,
  signal?: AbortSignal,
): Promise<AthleteFeaturesResponse> {
  const form = new FormData()
  for (const f of batch) {
    form.append('frames', f.jpeg, `f${f.index}.jpg`)
    form.append('t', String(f.t))
  }
  form.append('boxes', JSON.stringify(boxesOf(tracks, batch)))
  form.append('orig_width', String(tracks.video.width))
  form.append('orig_height', String(tracks.video.height))
  return apiUpload<AthleteFeaturesResponse>('/athletes/features', form, { signal })
}

/** Filtro final: une la medición por cuadro con la posición del grupo que dieron las zonas. */
export function resolveAthletes(
  features: AthleteFrameFeatures[],
  zones: ZonesResult,
  options: AthleteOptions,
  signal?: AbortSignal,
): Promise<AthletesResult> {
  return apiPost<AthletesResult>(
    '/athletes/', // el slash final importa: sin él hay un 307 que puede perder el cuerpo
    {
      source: 'upload',
      t0: options.t0,
      field_size: options.fieldSize,
      frames: features,
      group: zones.frames.map((z) => ({ x: z.x, v: z.v, cut: z.cut })),
    },
    { signal },
  )
}
