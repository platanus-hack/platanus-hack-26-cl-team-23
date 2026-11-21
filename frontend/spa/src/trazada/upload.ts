// Video subido por el usuario (arrastrar un archivo o pegar un enlace).
//
// Flujo: revisar duración → sacar cuadros → mandarlos al detector en lotes → armar un
// TracksJson (el mismo formato de Andrés) → buildRace(). Se procesa ANTES de reproducir,
// para que en el escenario se vea fluido; igual es causal, cada cuadro solo usa los anteriores.

import type { TracksJson } from './types'

/** Tope para la demo: una curva de 115 m a ritmo de medio fondo son ~16 s. */
export const MAX_SECONDS = 20
/** Cuadros por segundo que se le mandan al detector. */
export const SAMPLE_FPS = 10
/** El backend acepta hasta 24 cuadros por petición. */
const BATCH = 24
/** Ancho máximo del JPEG que viaja al detector (más chico = más rápido). */
const MAX_FRAME_W = 960

export type VideoInfo = { duration: number; width: number; height: number }
export type Frame = { index: number; t: number; jpeg: Blob }
export type Detection = TracksJson['frames'][number]['detections'][number]

/**
 * Detector: recibe un lote de cuadros y devuelve, por cuadro, las cajas en píxeles del
 * video original. AQUÍ se enchufa el de Andrés (POST /api/tracking/detect).
 */
export type Detector = (frames: Frame[], video: VideoInfo) => Promise<Detection[][]>

/** Detector de mentira mientras Andrés conecta el real: no encuentra a nadie. */
export const pendingDetector: Detector = async (frames) => {
  await new Promise((r) => setTimeout(r, 120))
  return frames.map(() => [])
}

export class UploadError extends Error {}

/** ¿Es un enlace de una plataforma (YouTube, Instagram…) que no entrega el archivo de video? */
export function isPlatformLink(url: string) {
  return /youtu\.?be|instagram\.com|tiktok\.com|vimeo\.com|facebook\.com/i.test(url)
}

function loadVideo(src: string): Promise<HTMLVideoElement> {
  return new Promise((resolve, reject) => {
    const v = document.createElement('video')
    v.crossOrigin = 'anonymous' // sin esto no se pueden leer los cuadros de un enlace externo
    v.muted = true
    v.preload = 'auto'
    v.playsInline = true
    v.onloadedmetadata = () => resolve(v)
    v.onerror = () => reject(new UploadError('No pudimos abrir ese video. Prueba con un .mp4 o .mov.'))
    v.src = src
  })
}

/** Lee duración y tamaño sin reproducir el video. */
export async function probeVideo(src: string): Promise<VideoInfo> {
  const v = await loadVideo(src)
  return { duration: v.duration, width: v.videoWidth, height: v.videoHeight }
}

/** Saca un cuadro cada 1/SAMPLE_FPS segundos, como JPEG. */
async function* extractFrames(src: string, info: VideoInfo, signal?: AbortSignal): AsyncGenerator<Frame> {
  const v = await loadVideo(src)
  const scale = Math.min(1, MAX_FRAME_W / info.width)
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(info.width * scale)
  canvas.height = Math.round(info.height * scale)
  const ctx = canvas.getContext('2d')!
  const total = Math.floor(info.duration * SAMPLE_FPS)

  for (let i = 0; i < total; i++) {
    if (signal?.aborted) return
    const t = i / SAMPLE_FPS
    await new Promise<void>((resolve) => {
      v.onseeked = () => resolve()
      v.currentTime = t
    })
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
    let dataUrl: string
    try {
      // toDataURL (síncrono) y no toBlob: el navegador deja toBlob en una cola de baja
      // prioridad y en la app de escritorio tardaba 1 s por cuadro; así son ~10 ms.
      dataUrl = canvas.toDataURL('image/jpeg', 0.8)
    } catch {
      // El sitio del enlace no permite leer sus cuadros (CORS).
      throw new UploadError('Ese enlace no deja leer sus cuadros. Descarga el video y arrástralo aquí.')
    }
    yield { index: i, t, jpeg: dataUrlToBlob(dataUrl) }
  }
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [head, b64] = dataUrl.split(',')
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  return new Blob([bytes], { type: head.slice(5, head.indexOf(';')) })
}

export type Progress = { done: number; total: number }

/** Procesa todo el video y devuelve el seguimiento en el formato de Andrés. */
export async function processVideo(
  src: string,
  info: VideoInfo,
  onProgress: (p: Progress) => void,
  { detector = pendingDetector, signal }: { detector?: Detector; signal?: AbortSignal } = {},
): Promise<TracksJson> {
  const total = Math.floor(info.duration * SAMPLE_FPS)
  const frames: TracksJson['frames'] = []
  let batch: Frame[] = []

  const flush = async () => {
    if (batch.length === 0) return
    const dets = await detector(batch, info)
    batch.forEach((f, i) => frames.push({ frame: f.index, t: f.t, detections: dets[i] ?? [] }))
    batch = []
    onProgress({ done: frames.length, total })
  }

  onProgress({ done: 0, total })
  for await (const f of extractFrames(src, info, signal)) {
    batch.push(f)
    if (batch.length === BATCH) await flush()
  }
  await flush()
  if (signal?.aborted) throw new UploadError('Cancelado')

  return {
    video: {
      source: 'subido',
      width: info.width,
      height: info.height,
      fps_out: SAMPLE_FPS,
      frames: frames.length,
      duration_s: info.duration,
    },
    tracks: summarizeTracks(frames),
    frames,
  }
}

/** Primer y último instante, y cuántas veces se vio, de cada corredor. */
function summarizeTracks(frames: TracksJson['frames']): TracksJson['tracks'] {
  const by = new Map<number, { t_start: number; t_end: number; n_obs: number }>()
  for (const f of frames)
    for (const d of f.detections) {
      const tr = by.get(d.id)
      if (tr) {
        tr.t_end = f.t
        tr.n_obs++
      } else by.set(d.id, { t_start: f.t, t_end: f.t, n_obs: 1 })
    }
  return [...by].map(([id, tr]) => ({ id, ...tr, on_track: 1 }))
}
