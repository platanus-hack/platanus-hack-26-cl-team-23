import type { components } from '../types/api.gen'
import type { Vec2 } from './geometry'

// =====================================================================
// 1) Contratos de la API. Vienen del OpenAPI del orchestrator (`make types`):
//    si un esquema cambia en Python, el build del front falla.
// =====================================================================

/** `POST /api/tracking/track` · corredores seguidos (RF-DETR + ByteTrack). */
export type TrackingResult = components['schemas']['TrackingResult']
export type DetectResponse = components['schemas']['DetectResponse']
export type AnalyzeResponse = components['schemas']['AnalyzeResponse']

/** `POST /api/zones/` · en qué zona de la pista enfoca la cámara en cada cuadro. */
export type ZonesResult = components['schemas']['ZonesResult']

/** `POST /api/athletes/` · posición y velocidad de cada atleta respecto a la cancha. */
export type AthletesResult = components['schemas']['AthletesResult']

/** `POST /api/tactics/` · pronóstico del final y mejores momentos para adelantar (un modelo, no una medición). */
export type TacticsResult = components['schemas']['TacticsResult']
export type TacticsStep = components['schemas']['TacticsStep']
export type ForecastAthlete = components['schemas']['ForecastAthlete']
export type Attack = components['schemas']['Attack']

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
  /** Resumen de todo el clip. Solo si se corrió el módulo de atletas. */
  summary?: AthleteSummary
}

/** Lo que el módulo de atletas midió de un corredor a lo largo del clip. */
export type AthleteSummary = {
  avgV: number // velocidad media respecto a la cancha (m/s)
  maxV: number
  meters: number // metros recorridos mientras se le midió
  extraM: number // metros de más por correr por fuera de la calle 1 en las curvas (estimado)
  startRank: number // puesto la primera vez que se le midió
  endRank: number // puesto la última vez
}

/** Un atleta en un cuadro, tal como lo entrega /api/athletes/. */
export type AthleteSample = {
  id: number
  trackId: number | null // id del tracker de imagen en este cuadro, si se ve
  rank: number
  x: number // metros desde la salida
  s: number // metros desde la meta (0-400)
  d: number // metros al bordillo
  lane: number // 1 = la de adentro
  v: number // m/s respecto a la cancha
  u: number // m/s respecto al grupo
  visible: boolean // medido en este cuadro (si no, su posición es una predicción)
  sigmaX: number // incertidumbre de x (m)
}

export type RunnerSample = {
  id: number
  bbox: [number, number, number, number] // x1, y1, x2, y2 en píxeles del video
  footPx: Vec2 // centro de la base de la caja = dónde pisa
  conf: number
  /** Id en la lista de corredores: el del atleta si hay datos de atletas, si no el del tracker. */
  rid?: number
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
  /** Atletas del cuadro. Solo si se corrió el módulo de atletas. */
  athletes?: AthleteSample[]
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
  /** Hay posición y velocidad por atleta (módulo de atletas). */
  hasAthletes?: boolean
  /** Corredor preseleccionado: el que se siguió por más tiempo. */
  defaultId?: number
  /** Respuestas originales de la API, para pedir el relato sin volver a procesar el video. */
  raw: { tracks: TrackingResult; zones?: ZonesResult; athletes?: AthletesResult }
}
