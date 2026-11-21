import type { components } from '../types/api.gen'
import type { Vec2 } from './geometry'

// =====================================================================
// 1) Contratos de la API. Vienen del OpenAPI del orchestrator (`make types`):
//    si un esquema cambia en Python, el build del front falla.
// =====================================================================

/** `POST /api/tracking/track` · corredores seguidos (RF-DETR + ByteTrack). */
export type TrackingResult = components['schemas']['TrackingResult']
export type DetectResponse = components['schemas']['DetectResponse']

/** `POST /api/zones/` · en qué zona de la pista enfoca la cámara en cada cuadro. */
export type ZonesResult = components['schemas']['ZonesResult']

// =====================================================================
// 2) Modelo INTERNO: lo único que conoce el dibujo. Todo lo de aquí sale
//    de los contratos de arriba; no hay datos inventados.
// =====================================================================

export type RunnerInfo = {
  id: number
  label: string // "#id"
  color: string
  tStart: number // primer y último instante en que se le siguió (s)
  tEnd: number
  nObs: number // cuántas veces se le vio
  onTrack: number // fracción (0-1) de color pista bajo los pies: qué tan seguro va en pista
}

export type RunnerSample = {
  id: number
  bbox: [number, number, number, number] // x1, y1, x2, y2 en píxeles del video
  footPx: Vec2 // centro de la base de la caja = dónde pisa
  conf: number
}

export type RaceFrame = {
  t: number
  runners: RunnerSample[]
  /** Zona (1..6) que enfoca la cámara. Solo si se corrió el módulo de zonas. */
  zone?: number
  /** Metros desde la meta del punto que enfoca la cámara (0-400). */
  focusS?: number
  /** Velocidad del punto enfocado (m/s). */
  focusV?: number
  /** Este cuadro empieza un plano nuevo. */
  cut?: boolean
}

/** Lectura de la cámara sobre la pista, tal como la entrega /api/zones/. */
export type CameraRead = {
  names: Record<number, string> // nombres de las zonas
  span: [number, number] // tramo de pista (m desde la meta) que recorrió el encuadre
  cuts: number[] // segundos en que cambia el plano
}

export type Race = {
  title: string
  note?: string // aviso para quien mira
  video: { width: number; height: number; duration: number; url?: string }
  /** Qué detector y qué tracker produjeron esto (`pipeline` de /track). */
  pipeline?: { detector: string; tracker: string }
  runners: RunnerInfo[]
  frames: RaceFrame[] // ordenados por t
  camera?: CameraRead
  /** Corredor preseleccionado: el que se siguió por más tiempo. */
  defaultId?: number
  /** Respuestas originales de la API, para pedir el relato sin volver a procesar el video. */
  raw: { tracks: TrackingResult; zones?: ZonesResult }
}
