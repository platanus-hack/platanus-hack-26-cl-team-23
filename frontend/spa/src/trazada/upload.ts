// Video subido por el usuario (arrastrar un archivo o pegar un enlace).
//
// Flujo: revisar duración → sacar cuadros → mandarlos al backend en lotes
// (POST /api/tracking/analyze: detección y evidencia de zonas con UNA sola subida por lote)
// → una sola llamada a POST /api/tracking/track que devuelve el seguimiento con ids
// → con esos ids y las zonas, POST /api/athletes/features (mismos cuadros, en lotes seguidos)
//   y POST /api/athletes/: posición y velocidad de cada atleta.
// El video nunca se sube: solo viajan los cuadros, ya reescalados.
//
// Se procesa ANTES de reproducir, para que en el escenario se vea fluido; igual es
// causal, cada cuadro solo usa los anteriores.

import { ApiError, apiPost, apiUpload } from '../lib/api'
import {
  ATHLETE_BATCH,
  type AthleteOptions,
  measureAthletes,
  resolveAthletes,
} from './athletes'
import type { AnalyzeResponse, AthletesResult, DetectResponse, TrackingResult, ZonesResult } from './types'
import { type ZoneOptions, resolveZones } from './zones'

/** Tope para la demo: una curva de 115 m a ritmo de medio fondo son ~16 s. */
export const MAX_SECONDS = 20
/** Cuadros por segundo que se le mandan al detector. */
export const SAMPLE_FPS = 10
/** El backend acepta hasta 24 cuadros por petición (MAX_BATCH_FRAMES). */
const BATCH = 24
/** Lotes en vuelo a la vez. El detector es serverless: en paralelo rinde mucho más. */
const CONCURRENCY = 3
/** Ancho máximo del JPEG que viaja al detector (más chico = más rápido). */
const MAX_FRAME_W = 960
/** Tope por cuadro del backend (MAX_FRAME_BYTES). */
const MAX_FRAME_BYTES = 1_500_000

export type VideoInfo = { duration: number; width: number; height: number }
export type Frame = { index: number; t: number; jpeg: Blob }

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
    let jpeg = encode(canvas, 0.8)
    // El backend rechaza cuadros de más de 1,5 MB: con un video muy detallado, bajamos calidad.
    if (jpeg.size > MAX_FRAME_BYTES) jpeg = encode(canvas, 0.5)
    yield { index: i, t, jpeg }
  }
}

function encode(canvas: HTMLCanvasElement, quality: number): Blob {
  let dataUrl: string
  try {
    // toDataURL (síncrono) y no toBlob: el navegador deja toBlob en una cola de baja
    // prioridad y en la app de escritorio tardaba 1 s por cuadro; así son ~10 ms.
    dataUrl = canvas.toDataURL('image/jpeg', quality)
  } catch {
    // El sitio del enlace no permite leer sus cuadros (CORS).
    throw new UploadError('Ese enlace no deja leer sus cuadros. Descarga el video y arrástralo aquí.')
  }
  const [head, b64] = dataUrl.split(',')
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  return new Blob([bytes], { type: head.slice(5, head.indexOf(';')) })
}

export type Phase = 'extracting' | 'detecting' | 'tracking' | 'measuring'
export type Progress = { phase: Phase; done: number; total: number }

export type ProcessOptions = {
  signal?: AbortSignal
  /** Zonas de la pista: si se omite, no se llama al módulo de zonas. */
  zones?: ZoneOptions
  /** Posición y velocidad por atleta. Necesita las zonas; si se omite, no se calculan. */
  athletes?: AthleteOptions
  /** Seguimiento de los primeros lotes ya detectados, para ir mostrando el video mientras se procesa. */
  onPartial?: (tracks: TrackingResult) => void
}

export type ProcessResult = { tracks: TrackingResult; zones?: ZonesResult; athletes?: AthletesResult }

/** Procesa todo el video contra el backend y devuelve el seguimiento con ids. */
export async function processVideo(
  src: string,
  info: VideoInfo,
  onProgress: (p: Progress) => void,
  { signal, zones, athletes, onPartial }: ProcessOptions = {},
): Promise<ProcessResult> {
  const total = Math.floor(info.duration * SAMPLE_FPS)
  if (total < 2) throw new UploadError('El video es demasiado corto para analizarlo.')

  // 1) Extraer. Un solo pase: los mismos JPEG alimentan al detector y a las zonas.
  onProgress({ phase: 'extracting', done: 0, total })
  const frames: Frame[] = []
  for await (const f of extractFrames(src, info, signal)) {
    frames.push(f)
    onProgress({ phase: 'extracting', done: frames.length, total })
  }
  if (signal?.aborted) throw new UploadError('Cancelado')

  // 2) Detectar por lotes, en paralelo. Cada lote sube una sola vez: el mismo envío da las
  // cajas y la evidencia de zonas.
  const batches: Frame[][] = []
  for (let i = 0; i < frames.length; i += BATCH) batches.push(frames.slice(i, i + BATCH))

  let done = 0
  let zonesOk = zones !== undefined
  // Vista previa: ByteTrack es causal, así que correrlo sobre los primeros lotes ya listos da
  // los mismos ids que tendrá el resultado final. Una sola corrida en vuelo a la vez.
  const detectedBatches: (DetectResponse | undefined)[] = new Array(batches.length)
  let previewed = 0
  let previewing = false
  let live = onPartial !== undefined
  const preview = () => {
    if (!live || previewing) return
    let ready = 0
    while (detectedBatches[ready]) ready++
    if (ready === previewed) return
    previewed = ready
    previewing = true
    const covered = detectedBatches.slice(0, ready).flatMap((d) => d!.frames)
    apiPost<TrackingResult>('/tracking/track', trackRequest(info, covered), { signal })
      .then((partial) => live && onPartial?.(partial))
      .catch(() => {}) // es solo una vista previa
      .finally(() => {
        previewing = false
        preview()
      })
  }

  onProgress({ phase: 'detecting', done, total: frames.length })
  const results = await pool(batches, CONCURRENCY, async (batch, i) => {
    const { detect, zones: features } = await retry(() => analyzeBatch(batch, info, zones !== undefined, signal))
    // Las zonas son un extra: si faltan en algún lote, la carrera se arma igual con el seguimiento.
    if (zones && !features) zonesOk = false
    done += batch.length
    onProgress({ phase: 'detecting', done, total: frames.length })
    detectedBatches[i] = detect
    preview()
    return { detected: detect, features }
  })
  live = false
  if (signal?.aborted) throw new UploadError('Cancelado')

  // 3) Trackear todo de una vez: ByteTrack necesita la secuencia completa.
  onProgress({ phase: 'tracking', done: 0, total: 1 })
  const tracks = await apiPost<TrackingResult>(
    '/tracking/track',
    trackRequest(
      info,
      results.flatMap((r) => r.detected.frames),
    ),
    { signal },
  )

  // Solo sirven si están TODOS los lotes: el filtro une zonas y seguimiento por el número
  // de cuadro, y un hueco correría los índices.
  const zoneResult =
    zones && zonesOk
      ? await resolveZones(results.flatMap((r) => r.features!.frames), zones, signal).catch(() => undefined)
      : undefined

  onProgress({ phase: 'tracking', done: 1, total: 1 })

  // 4) Atletas: es un extra, igual que las zonas. Si algo falla se muestra lo demás.
  const athleteResult =
    athletes && zoneResult && zoneResult.frames.length === frames.length
      ? await measure(frames, tracks, zoneResult, athletes, onProgress, signal).catch(() => undefined)
      : undefined

  return { tracks, zones: zoneResult, athletes: athleteResult }
}

/** Mide a cada atleta: lotes de cuadros seguidos en paralelo, y un filtro final con el grupo. */
async function measure(
  frames: Frame[],
  tracks: TrackingResult,
  zones: ZonesResult,
  options: AthleteOptions,
  onProgress: (p: Progress) => void,
  signal?: AbortSignal,
): Promise<AthletesResult> {
  const batches: Frame[][] = []
  for (let i = 0; i < frames.length; i += ATHLETE_BATCH) batches.push(frames.slice(i, i + ATHLETE_BATCH))

  let done = 0
  onProgress({ phase: 'measuring', done, total: frames.length })
  const results = await pool(batches, CONCURRENCY, async (batch) => {
    const measured = await retry(() => measureAthletes(batch, tracks, signal))
    done += batch.length
    onProgress({ phase: 'measuring', done, total: frames.length })
    return measured
  })
  return resolveAthletes(
    results.flatMap((r) => r.frames),
    zones,
    options,
    signal,
  )
}

function trackRequest(info: VideoInfo, frames: DetectResponse['frames']) {
  return {
    source: 'upload',
    width: info.width,
    height: info.height,
    fps_out: SAMPLE_FPS,
    frames: frames.map((f) => ({ t: f.t, dets: f.dets })),
  }
}

/** Detecta y, si se pide, saca la evidencia de zonas del lote: los cuadros viajan una sola vez. */
function analyzeBatch(
  batch: Frame[],
  info: VideoInfo,
  withZones: boolean,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  const form = new FormData()
  // Las cajas vuelven en píxeles del video original: el backend reescala con orig_*.
  for (const f of batch) {
    form.append('frames', f.jpeg, `f${f.index}.jpg`)
    form.append('t', String(f.t))
  }
  form.append('orig_width', String(info.width))
  form.append('orig_height', String(info.height))
  form.append('with_zones', String(withZones))
  return apiUpload<AnalyzeResponse>('/tracking/analyze', form, { signal })
}

/** El detector es serverless: un 502 o un 429 sueltos se reintentan una vez. */
async function retry<T>(fn: () => Promise<T>, attempts = 2): Promise<T> {
  for (let i = 1; ; i++) {
    try {
      return await fn()
    } catch (e) {
      if (i >= attempts || !(e instanceof ApiError) || !e.retryable) throw e
      await new Promise((r) => setTimeout(r, 400 * i))
    }
  }
}

/** Ejecuta `fn` sobre todos los items con como máximo `limit` en vuelo, conservando el orden. */
async function pool<T, R>(items: T[], limit: number, fn: (item: T, index: number) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length)
  let next = 0
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      for (let i = next++; i < items.length; i = next++) out[i] = await fn(items[i], i)
    }),
  )
  return out
}
