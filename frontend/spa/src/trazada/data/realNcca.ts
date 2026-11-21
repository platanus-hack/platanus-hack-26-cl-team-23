// DATOS REALES · video NCCA de Andrés + su seguimiento (RF-DETR + ByteTrack).
//
// Se leen directo desde backend/orchestrator/app/assets: Vite los sirve en desarrollo
// y los copia al build. Falta la geometría de Daniel: cuando exista su JSON,
// se importa aquí igual y se pasa como segundo argumento de buildRace().

import videoUrl from '../../../../../backend/orchestrator/app/assets/NCCA.mp4?url'
import tracksUrl from '../../../../../backend/orchestrator/app/assets/out/NCCA.tracks.json?url'
import type { RaceMeta } from '../adapter'
import type { GeometryJson, TracksJson } from '../types'

export async function load(): Promise<{ tracks: TracksJson; geometry?: GeometryJson; meta: RaceMeta }> {
  const res = await fetch(tracksUrl)
  if (!res.ok) throw new Error(`No se pudo leer el seguimiento de Andrés (${res.status})`)
  const tracks = (await res.json()) as TracksJson
  return {
    tracks,
    geometry: undefined,
    meta: { title: 'Video real · NCCA', isMock: false, videoUrl },
  }
}
