import { useEffect, useRef, useState } from 'react'
import { buildRace, frameAt } from '../../trazada/adapter'
import { fmtNum } from '../../trazada/format'
import type { Race } from '../../trazada/types'
import {
  MAX_SECONDS,
  UploadError,
  isPlatformLink,
  probeVideo,
  processVideo,
  type Progress,
} from '../../trazada/upload'
import { DEFAULT_ATHLETE_OPTIONS } from '../../trazada/athletes'
import { usePlayback } from '../../trazada/usePlayback'
import { DEFAULT_DISTANCE, PRUEBAS, describeStart } from '../../trazada/pruebas'
import { ApiError } from '../../lib/api'
import { CameraView } from './CameraView'
import { Button, Figure, TrackMark } from './ui'

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
  measuring: 'midiendo posición y velocidad',
}

/** Las fases pesan distinto: detectar es lo lento (va contra el servidor). */
const PHASE_RANGE: Record<Progress['phase'], [number, number]> = {
  extracting: [0, 0.3],
  detecting: [0.3, 0.75],
  tracking: [0.75, 0.8],
  measuring: [0.8, 1],
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
  const [distance, setDistance] = useState(DEFAULT_DISTANCE)
  const [shot, setShot] = useState('0')
  // Seguimiento de los primeros lotes ya detectados: es lo que se ve mientras el resto se procesa.
  const [preview, setPreview] = useState<Race | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])

  async function start(src: string, name: string, isLocal: boolean) {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    setState({ kind: 'checking' })
    setPreview(null)
    try {
      const info = await probeVideo(src)
      if (info.duration > MAX_SECONDS + 0.5) {
        throw new UploadError(
          `Dura ${fmtNum(info.duration, 0)} s. Para la demo el tope es ${MAX_SECONDS} s: recórtalo a una sola curva.`,
        )
      }
      // El disparo se escribe con coma o punto; si no es un número, se toma como el inicio del clip.
      const t0 = Number.parseFloat(shot.replace(',', '.'))
      const gun = Number.isFinite(t0) ? t0 : 0
      setState({ kind: 'processing', name, src, progress: { phase: 'extracting', done: 0, total: 1 } })
      const { tracks, zones, athletes } = await processVideo(
        src,
        info,
        (progress) => setState({ kind: 'processing', name, src, progress }),
        {
          signal: ctrl.signal,
          onPartial: (partial) => setPreview(buildRace(partial, undefined, undefined, { title: name, videoUrl: src })),
          zones: { distance, t0: gun },
          athletes: { ...DEFAULT_ATHLETE_OPTIONS, t0: gun, distance },
        },
      )
      onReady(
        buildRace(tracks, zones, athletes, {
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
      <Figure title="Reconstruyendo la carrera" meta={`${Math.round(pct * 100)} %`}>
        <div className="flex flex-col gap-6 md:flex-row md:items-start">
          {state.kind === 'processing' &&
            (preview ? (
              <LivePreview race={preview} />
            ) : (
              <video src={state.src} muted playsInline className="aspect-video w-full rounded-inner bg-fg object-cover md:w-80" />
            ))}
          <div className="min-w-0 flex-1">
            <p className="text-2xl leading-tight font-semibold tracking-[-0.01em]" aria-live="polite">
              {state.kind === 'checking' ? 'Revisando el video…' : `${capitalize(PHASE_LABEL[state.progress.phase])}…`}
            </p>
            {state.kind === 'processing' && (
              <>
                <p className="label mt-2 truncate text-muted">{state.name}</p>
                <FrameGrid progress={state.progress} />
              </>
            )}
          </div>
        </div>
      </Figure>
    )
  }

  return (
    <Figure title="Sube el video de una carrera">
      {/* 0. Qué prueba es: de ahí sale el punto de partida en la pista */}
      <div className="mb-6 grid gap-4 md:max-w-2xl md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <label htmlFor="prueba" className="text-sm font-semibold">
            ¿Qué prueba es?
          </label>
          <select
            id="prueba"
            value={distance}
            onChange={(e) => setDistance(Number(e.target.value))}
            aria-describedby="prueba-help"
            className="min-h-11 rounded-inner border border-line bg-surface px-3 text-base focus-visible:border-accent focus-visible:outline-2"
          >
            {PRUEBAS.map((p) => (
              <option key={p.distance} value={p.distance}>
                {p.label}
              </option>
            ))}
          </select>
          <p id="prueba-help" className="text-sm text-muted">
            {describeStart(distance)}
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <label htmlFor="disparo" className="text-sm font-semibold">
            Segundo del disparo en el video
          </label>
          <input
            id="disparo"
            type="text"
            inputMode="decimal"
            value={shot}
            onChange={(e) => setShot(e.target.value)}
            aria-describedby="disparo-help"
            className="min-h-11 rounded-inner border border-line bg-surface px-3 text-base tabular-nums focus-visible:border-accent focus-visible:outline-2"
          />
          <p id="disparo-help" className="text-sm text-muted">
            0 si el video parte con la salida. Si la carrera ya iba, los segundos que habían pasado, con signo menos (−40).
          </p>
        </div>
      </div>

      {/* 1. Archivo: la caja trae sus propias reglas */}
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
        className={`sky flex min-h-80 w-full flex-col items-center justify-center gap-3 overflow-hidden rounded-inner px-6 py-10 text-center transition-transform duration-300 ease-[var(--ease-out)] ${
          dragging ? 'scale-[0.985]' : 'hover:scale-[0.995]'
        } focus-visible:outline-2 focus-visible:outline-offset-2`}
      >
        <span className="relative z-10 grid h-14 w-14 place-items-center rounded-inner bg-surface">
          <TrackMark className="h-9 w-9" />
        </span>
        <span className="stat-number relative z-10">{dragging ? 'Suéltalo' : 'Arrastra el video aquí'}</span>
        <span className="relative z-10 text-sm text-fg/80">o haz clic para elegirlo</span>
        <span className="label relative z-10 mt-4 rounded-ui bg-surface/70 px-3 py-1 text-fg">
          MP4 o MOV · hasta {MAX_SECONDS} s · una sola curva
        </span>
      </button>
      <input
        ref={input}
        type="file"
        accept="video/*"
        aria-label="Elegir un video de tu computador"
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0])}
      />

      {/* 2. Enlace: primero el campo, después su regla */}
      <form onSubmit={onLink} className="mt-6 flex flex-col gap-2 md:max-w-2xl">
        <label htmlFor="video-link" className="text-sm font-semibold">
          O usa un enlace
        </label>
        <div className="flex gap-2">
          <input
            id="video-link"
            name="video-link"
            type="url"
            autoComplete="url"
            spellCheck={false}
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="https://…/carrera.mp4"
            aria-describedby="video-link-help"
            className="min-h-11 min-w-0 flex-1 rounded-inner border border-line bg-surface px-3 text-base placeholder:text-other focus-visible:border-accent focus-visible:outline-2"
          />
          <Button type="submit" variant="primary">
            Analizar
          </Button>
        </div>
        <p id="video-link-help" className="label text-muted">
          Enlace directo al archivo .mp4 · YouTube e Instagram no sirven
        </p>
      </form>

      {state.kind === 'error' && (
        <p role="alert" className="mt-4 rounded-inner bg-band px-3 py-2 text-sm text-fg">
          {state.message}
        </p>
      )}
    </Figure>
  )
}

/**
 * El video con los corredores ya detectados, en bucle sobre lo que va listo. El reloj corre
 * solo hasta donde llegó el seguimiento, así que las cajas nunca se quedan congeladas.
 */
function LivePreview({ race }: { race: Race }) {
  const { t, playing } = usePlayback(race.video.duration)
  return (
    <div className="w-full overflow-hidden rounded-inner md:w-[26rem]">
      <CameraView
        race={race}
        frameIndex={frameAt(race.frames, t)}
        t={t}
        playing={playing}
        showOverlay
        selectedId={undefined}
        onSelect={() => {}}
      />
    </div>
  )
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/**
 * Un punto por cuadro del video, en las tres fases reales del proceso:
 * sacado del video (gris), procesado por el detector (tinta, la barra gira), último lote (naranja).
 */
function FrameGrid({ progress }: { progress: Progress }) {
  // El total de cuadros se fija en las dos primeras fases; en "siguiendo" ya están todos.
  const [n, setN] = useState(1)
  const latest = progress.phase !== 'tracking' ? Math.max(1, progress.total) : n
  if (latest !== n) setN(latest) // ajustar estado durante el render: patrón recomendado por React
  const extracted = progress.phase === 'extracting' ? progress.done : n
  const detected = progress.phase === 'detecting' ? progress.done : progress.phase === 'tracking' ? n : 0
  const fresh = Math.max(0, detected - 24)
  return (
    <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(14px,1fr))] gap-1" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => {
        const isDetected = i < detected
        const isFresh = isDetected && i >= fresh && progress.phase === 'detecting'
        const isExtracted = i < extracted
        return (
          <span
            key={i}
            className={`grid aspect-square place-items-center rounded-full transition-colors duration-500 ${
              isFresh ? 'bg-pick' : isDetected ? 'bg-fg' : isExtracted ? 'bg-line' : 'bg-paper2'
            }`}
          >
            <span
              className={`h-[55%] w-[1.5px] rounded-full transition-transform duration-500 ease-[var(--ease-out)] ${
                isDetected ? '-rotate-45 bg-white' : 'rotate-45 bg-other'
              }`}
            />
          </span>
        )
      })}
    </div>
  )
}
