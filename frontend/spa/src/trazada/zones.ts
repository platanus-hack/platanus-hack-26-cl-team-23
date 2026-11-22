// Zonas de la pista: en qué tramo (Z1..Z6) enfoca la cámara en cada cuadro.
//
// Dos pasos, igual que el seguimiento: evidencia visual por lote (sale de
// POST /api/tracking/analyze, en la misma subida que la detección) y un filtro final
// sobre todo el video (POST /api/zones/).
//
// Esto dice dónde mira la CÁMARA, no dónde está cada corredor: sirve para ubicar el
// encuadre en la pista, no para medir a los atletas.

import { apiPost } from '../lib/api'
import type { ZonesResult } from './types'
import type { components } from '../types/api.gen'

type ZoneFeaturesResponse = components['schemas']['ZoneFeaturesResponse']
type ZoneFeaturesInput = components['schemas']['ZoneFeaturesInput']

export type ZoneOptions = {
  /** Metros de la prueba: define la salida y el ritmo esperado. */
  distance: number
  /** Segundo del video en que suena el disparo (reloj de carrera). */
  t0: number
}

/** La apariencia y la curvatura solo hacen falta cada ~0,5 s; el histograma, en todos. */
const DESC_EVERY_S = 0.5

/** Filtro de zonas sobre todas las features acumuladas. */
export async function resolveZones(
  features: ZoneFeaturesResponse['frames'],
  options: ZoneOptions,
  signal?: AbortSignal,
): Promise<ZonesResult | undefined> {
  if (features.length === 0) return undefined

  let nextSample = -Infinity
  const frames: ZoneFeaturesInput[] = features.map((f) => {
    const withDesc = f.t >= nextSample
    if (withDesc) nextSample = f.t + DESC_EVERY_S
    return withDesc
      ? { t: f.t, hist: f.hist, desc: f.desc, bend: f.bend, chord: f.chord, n: f.n }
      : { t: f.t, hist: f.hist }
  })

  return apiPost<ZonesResult>(
    '/zones/', // el slash final importa: sin él hay un 307 que puede perder el cuerpo
    { source: 'upload', distance: options.distance, t0: options.t0, frames },
    { signal },
  )
}
