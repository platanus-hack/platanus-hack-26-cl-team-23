// Relato del clip: POST /api/narration/.
//
// El backend resume los datos en una hoja de hechos, Claude escribe el guion y ElevenLabs
// lo lee. Aquí solo se manda lo que ya tenemos procesado (sin volver a tocar el video) y
// se recibe el texto por tramos con la duración real de cada audio.

import { apiPost } from '../lib/api'
import type { components } from '../types/api.gen'
import type { Race } from './types'

export type Narration = components['schemas']['NarrationResponse']
export type NarrationSegment = components['schemas']['NarrationSegment']

export type NarrationStyle = 'transmision' | 'analisis'

/** Repetir el mismo video sale de caché en el backend: no vuelve a gastar cuota. */
export function generateNarration(race: Race, style: NarrationStyle = 'transmision', signal?: AbortSignal) {
  return apiPost<Narration>(
    '/narration/',
    { tracks: race.raw.tracks, zones: race.raw.zones, athletes: race.raw.athletes, style, segment_s: 8 },
    { signal },
  )
}
