import type { Homography, Vec2 } from './geometry'

// =====================================================================
// 1) Formatos de ENTRADA: lo que entregan Andrés y Daniel.
//    Si el formato cambia, solo se tocan estos tipos y adapter.ts.
// =====================================================================

/** Andrés · seguimiento de corredores (formato real de NCCA.tracks.json). */
export type TracksJson = {
  video: {
    source: string
    width: number
    height: number
    fps_out: number
    frames: number
    duration_s: number
  }
  tracks: { id: number; t_start: number; t_end: number; n_obs: number; on_track: number }[]
  frames: {
    frame: number
    t: number
    detections: {
      id: number
      bbox: [number, number, number, number] // x1, y1, x2, y2 en píxeles
      foot_px: Vec2 // centro de la base de la caja = dónde pisa
      conf: number
    }[]
  }[]
}

/** Daniel · geometría de la pista (formato PROPUESTO, aún en discusión). */
export type GeometryJson = {
  frames: {
    frame: number
    t: number
    zone: number // 1..6: qué tramo de la pista mira la cámara
    H?: Homography // mundo (m) → imagen (px)
    runners: {
      id: number // mismo id que el track de Andrés
      s: number // metros por la línea de medición desde la meta
      d: number // distancia lateral a la cuerda
      v?: number // m/s
      extra_m: number // metros extra acumulados por ir por fuera
    }[]
  }[]
  summary?: { id: number; start_rank: number; end_rank: number; extra_m: number }[]
}

// =====================================================================
// 2) Modelo INTERNO: lo único que conoce el dibujo.
// =====================================================================

export type RunnerInfo = {
  id: number
  label: string // lo que se muestra: dorsal o "#id"
  color: string
  hero?: boolean // el corredor que cuenta la historia
  tStart?: number // primer y último instante en que se le siguió (s)
  tEnd?: number
}

export type RunnerSample = {
  id: number
  bbox?: [number, number, number, number]
  footPx?: Vec2
  s?: number
  d?: number
  extraM?: number
}

export type RaceFrame = {
  t: number
  zone?: number
  worldToImage?: Homography
  runners: RunnerSample[]
}

export type RunnerResult = {
  id: number
  startRank: number
  endRank: number
  extraM: number
}

export type Race = {
  title: string // "800 m · última curva"
  isMock: boolean
  video: { width: number; height: number; duration: number; url?: string }
  runners: RunnerInfo[]
  frames: RaceFrame[] // ordenados por t
  cameraSpan?: [number, number] // tramo (en s) que cubre la cámara, para resaltarlo en la vista cenital
  results: RunnerResult[]
  heroId?: number
}
