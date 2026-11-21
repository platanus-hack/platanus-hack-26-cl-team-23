import { useEffect, useRef, useState } from 'react'
import { buildRace } from '../../trazada/adapter'
import { fmtNum } from '../../trazada/format'
import type { Race } from '../../trazada/types'
import {
  MAX_SECONDS,
  SAMPLE_FPS,
  UploadError,
  isPlatformLink,
  probeVideo,
  processVideo,
  type Progress,
} from '../../trazada/upload'
import { DEFAULT_ZONE_OPTIONS } from '../../trazada/zones'
import { ApiError } from '../../lib/api'

type State =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'processing'; name: string; src: string; progress: Progress }
  | { kind: 'error'; message: string }

type Props = {
  onReady: (race: Race) => void
}

const PHASE_LABEL: Record<Progress['phase'], string> = {
  extracting: 'sacando cuadros del video',
  detecting: 'buscando corredores',
  tracking: 'siguiendo a cada corredor',
}

/** Las tres fases pesan distinto: detectar es lo lento (va contra el servidor). */
const PHASE_RANGE: Record<Progress['phase'], [number, number]> = {
  extracting: [0, 0.35],
  detecting: [0.35, 0.95],
  tracking: [0.95, 1],
}

function progressPct(p: Progress) {
  const [from, to] = PHASE_RANGE[p.phase]
  return from + (to - from) * (p.done / Math.max(1, p.total))
}

/**
 * Subir un video: arrastrar un archivo o pegar un enlace directo (.mp4).
 * El navegador lo reproduce sin subirlo; solo los cuadros viajan al detector.
 */
export function UploadPanel({ onReady }: Props) {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [dragging, setDragging] = useState(false)
  const [link, setLink] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])

  async function start(src: string, name: string, isLocal: boolean) {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    setState({ kind: 'checking' })
    try {
      const info = await probeVideo(src)
      if (info.duration > MAX_SECONDS + 0.5) {
        throw new UploadError(
          `Dura ${fmtNum(info.duration, 0)} s. Para la demo el tope es ${MAX_SECONDS} s: recórtalo a una sola curva.`,
        )
      }
      setState({ kind: 'processing', name, src, progress: { phase: 'extracting', done: 0, total: 1 } })
      const { tracks, zones } = await processVideo(
        src,
        info,
        (progress) => setState({ kind: 'processing', name, src, progress }),
        { signal: ctrl.signal, zones: DEFAULT_ZONE_OPTIONS },
      )
      onReady(
        buildRace(tracks, zones, {
          title: name,
          videoUrl: src,
          note:
            tracks.tracks.length === 0
              ? 'No encontramos corredores en este video. Prueba con una toma donde se vea la pista completa.'
              : undefined,
        }),
      )
    } catch (e) {
      if (ctrl.signal.aborted) return
      if (isLocal) URL.revokeObjectURL(src)
      const message =
        e instanceof UploadError || e instanceof ApiError
          ? e.message
          : isLocal
            ? 'No pudimos leer ese archivo. Prueba con un .mp4 o .mov.'
            : 'No pudimos abrir ese enlace. Descarga el video y arrástralo aquí.'
      setState({ kind: 'error', message })
    }
  }

  function onFile(file: File | undefined) {
    if (!file) return
    if (!file.type.startsWith('video/')) {
      setState({ kind: 'error', message: 'Ese archivo no es un video. Prueba con un .mp4 o .mov.' })
      return
    }
    start(URL.createObjectURL(file), file.name, true)
  }

  function onLink(e: React.FormEvent) {
    e.preventDefault()
    const url = link.trim()
    if (!url) return
    if (isPlatformLink(url)) {
      setState({
        kind: 'error',
        message: 'Los enlaces de YouTube, Instagram y similares no entregan el archivo. Descárgalo y arrástralo aquí.',
      })
      return
    }
    start(url, url.split('/').pop() || 'Video del enlace', false)
  }

  if (state.kind === 'processing' || state.kind === 'checking') {
    const pct = state.kind === 'processing' ? progressPct(state.progress) : 0
    return (
      <section className="rounded-xl border border-line bg-panel p-6" aria-live="polite">
        <div className="flex flex-col gap-6 md:flex-row md:items-center">
          {state.kind === 'processing' && (
            <video src={state.src} muted playsInline className="aspect-video w-full rounded-lg bg-black object-cover md:w-72" />
          )}
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-2xl leading-tight font-bold">
              {state.kind === 'checking' ? 'Revisando el video…' : 'Reconstruyendo la carrera…'}
            </h2>
            {state.kind === 'processing' && (
              <>
                <p className="mt-1 truncate text-sm text-muted">{state.name}</p>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-line">
                  <div className="h-full rounded-full bg-accent transition-[width] duration-200" style={{ width: `${pct * 100}%` }} />
                </div>
                <p className="mt-2 font-mono text-xs text-muted tabular-nums">
                  {PHASE_LABEL[state.progress.phase]}
                  {state.progress.phase !== 'tracking' && ` · cuadro ${state.progress.done} de ${state.progress.total}`}
                </p>
              </>
            )}
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-line bg-panel p-6">
      <div className="flex flex-col gap-6 lg:flex-row">
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            onFile(e.dataTransfer.files[0])
          }}
          className={`flex min-h-48 flex-1 flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
            dragging ? 'border-accent bg-accent/10' : 'border-line hover:border-muted'
          } focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`}
        >
          <UploadIcon />
          <span className="font-display text-2xl leading-tight font-bold">Arrastra el video de una curva</span>
          <span className="text-sm text-muted">o haz clic para elegirlo · .mp4 o .mov · hasta {MAX_SECONDS} s</span>
        </button>
        <input
          ref={input}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])}
        />

        <div className="flex flex-col gap-4 lg:w-80">
          <form onSubmit={onLink} className="flex flex-col gap-2">
            <label htmlFor="video-link" className="text-sm font-semibold">
              O pega un enlace directo
            </label>
            <div className="flex gap-2">
              <input
                id="video-link"
                type="url"
                value={link}
                onChange={(e) => setLink(e.target.value)}
                placeholder="https://…/carrera.mp4"
                className="min-h-10 min-w-0 flex-1 rounded-md border border-line bg-bg px-3 text-sm placeholder:text-muted/70 focus-visible:outline-2 focus-visible:outline-accent"
              />
              <button
                type="submit"
                className="min-h-10 rounded-md bg-accent px-4 text-sm font-semibold text-bg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Usar
              </button>
            </div>
          </form>
          <p className="text-sm text-muted">
            El video no se sube: el navegador saca {SAMPLE_FPS} cuadros por segundo y solo esos viajan al detector.
          </p>
          {state.kind === 'error' && (
            <p role="alert" className="rounded-md border border-red-400/40 bg-red-400/10 px-3 py-2 text-sm text-red-200">
              {state.message}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

const UploadIcon = () => (
  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="text-accent">
    <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
