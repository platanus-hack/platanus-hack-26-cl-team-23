// DATOS REALES · video NCCA de Andrés + su seguimiento (RF-DETR + ByteTrack).
//
// Son archivos estáticos del front (public/demo/): así la demo no depende del backend
// ni del almacenamiento de Andrés (los presets viven ahora en Vercel Blob). Falta la geometría de Daniel: cuando exista su JSON,
// se importa aquí igual y se pasa como segundo argumento de buildRace().

const videoUrl = '/demo/NCCA.mp4'
const tracksUrl = '/demo/NCCA.tracks.json'
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
