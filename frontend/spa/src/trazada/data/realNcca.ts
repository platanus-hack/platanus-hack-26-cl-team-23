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
  if (!res.ok || !res.headers.get('content-type')?.includes('json')) throw new Error('el ejemplo NCCA solo está en el computador de desarrollo por ahora (frontend/spa/public/demo)')
  const tracks = (await res.json()) as TracksJson
  return {
    tracks,
    geometry: undefined,
    meta: { title: 'Video real · NCCA', isMock: false, videoUrl },
  }
}
