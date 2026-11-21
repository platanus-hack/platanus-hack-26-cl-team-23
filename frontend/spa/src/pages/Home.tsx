import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { CameraView } from '../components/trazada/CameraView'
import { BalanceChart } from '../components/trazada/BalanceChart'
import { Leaderboard, ResultCard, RunnerStats } from '../components/trazada/ResultCard'
import { UploadPanel } from '../components/trazada/UploadPanel'
import { RunnerTelemetry } from '../components/trazada/RunnerTelemetry'
import { TopView } from '../components/trazada/TopView'
import { frameAt, loadRace, type RaceSource } from '../trazada/adapter'
import { ZONE_NAMES, runnerSeries } from '../trazada/analysis'
import { fmtSeconds } from '../trazada/format'
import type { Race } from '../trazada/types'
import { usePlayback } from '../trazada/usePlayback'

type Source = RaceSource | 'subir'

/** Pantalla principal de TRAZADA. */
export default function Home() {
  // La fuente va en la URL (?fuente=…) para poder compartir un link directo a cada modo.
  const [params, setParams] = useSearchParams()
  const raw = params.get('fuente')
  const source: Source = raw === 'simulacion' || raw === 'subir' ? raw : 'real'
  const setSource = (s: Source) => setParams(s === 'real' ? {} : { fuente: s })
  // El video subido vive solo en memoria: no se puede poner en la URL.
  const [uploaded, setUploaded] = useState<Race | null>(null)
  const replaceUpload = (race: Race | null) => {
    if (uploaded?.video.url?.startsWith('blob:')) URL.revokeObjectURL(uploaded.video.url)
    setUploaded(race)
  }

  // TanStack Query cachea cada fuente por separado: cambiar de modo y volver es instantáneo.
  const { data: race, isPending, isError, error } = useQuery({
    queryKey: ['race', source],
    queryFn: () => loadRace(source as RaceSource),
    enabled: source !== 'subir',
  })

  if (source === 'subir') {
    if (uploaded)
      return <RaceScreen key={uploaded.video.url} race={uploaded} source={source} onSource={setSource} onNewUpload={() => replaceUpload(null)} />
    return (
      <div className="flex flex-col gap-6">
        <SourceBar title="Analiza tu carrera" subtitle="Sube el video de una curva y TRAZADA sigue a cada corredor." source={source} onSource={setSource} />
        <UploadPanel onReady={replaceUpload} onUseExample={() => setSource('real')} />
      </div>
    )
  }
  if (isPending) return <p className="text-muted">Cargando carrera…</p>
  if (isError) return <p className="text-red-400">No se pudo cargar la carrera: {error.message}</p>
  // key: al cambiar de fuente, la pantalla parte de cero (tiempo, corredor elegido…)
  return <RaceScreen key={source} race={race} source={source} onSource={setSource} />
}

const SOURCES: [Source, string][] = [
  ['subir', 'Tu video'],
  ['real', 'Ejemplo NCCA'],
  ['simulacion', 'Simulación'],
]

function SourceBar({
  title,
  subtitle,
  source,
  onSource,
  action,
}: {
  title: string
  subtitle: string
  source: Source
  onSource: (s: Source) => void
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="font-display text-[32px] leading-none font-extrabold">{title}</h1>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        {action}
        <div role="group" aria-label="Fuente de datos" className="inline-flex rounded-lg border border-line p-0.5">
          {SOURCES.map(([value, text]) => (
            <button
              key={value}
              type="button"
              onClick={() => onSource(value)}
              aria-pressed={source === value}
              className={`min-h-9 rounded-md px-3 text-sm font-semibold transition-colors ${
                source === value ? 'bg-accent text-bg' : 'text-muted hover:text-fg'
              } focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`}
            >
              {text}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function RaceScreen({
  race,
  source,
  onSource,
  onNewUpload,
}: {
  race: Race
  source: Source
  onSource: (s: Source) => void
  onNewUpload?: () => void
}) {
  const { t, playing, toggle, seek } = usePlayback(race.video.duration)
  const [overlay, setOverlay] = useState(true)
  const [ghost, setGhost] = useState(true)
  const [selectedId, setSelectedId] = useState(race.heroId ?? race.runners[0]?.id)
  const series = useMemo(() => runnerSeries(race), [race])
  const fi = frameAt(race.frames, t)
  const frame = race.frames[fi]
  const selected = race.runners.find((r) => r.id === selectedId)
  const selSeries = selectedId !== undefined ? series.get(selectedId) : undefined
  const currentS = frame?.runners.find((r) => r.id === selectedId)?.s
  // ¿Llegó la geometría de Daniel? Sin ella no hay metros, puestos ni vista cenital.
  const hasGeometry = series.size > 0

  return (
    <div className="flex flex-col gap-6">
      <SourceBar
        title={race.title}
        subtitle={
          race.note ??
          (source === 'real'
            ? 'Corredores seguidos en el video con RF-DETR + ByteTrack'
            : 'Carrera simulada · todos los datos son inventados')
        }
        source={source}
        onSource={onSource}
        action={
          onNewUpload && (
            <button
              type="button"
              onClick={onNewUpload}
              className="min-h-9 rounded-md border border-line px-3 text-sm font-semibold text-fg hover:border-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Subir otro video
            </button>
          )
        }
      />

      {/* Fila 1: video + resultado y posiciones */}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="min-w-0 overflow-hidden rounded-xl border border-line bg-panel">
          <div className="relative">
            <CameraView
              race={race}
              frameIndex={fi}
              t={t}
              playing={playing}
              showOverlay={overlay}
              showGhost={ghost}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
            {/* HUD tipo transmisión */}
            <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-4">
              <span className="flex items-center gap-2 rounded bg-black/55 px-2 py-1 text-xs font-semibold backdrop-blur-sm">
                <span className={`h-2 w-2 rounded-full ${race.video.url ? 'bg-red-500' : 'bg-muted'}`} />
                {race.video.url ? 'Video' : 'Simulación'}
                <span className="font-mono text-fg/80 tabular-nums">{fmtSeconds(t)}</span>
              </span>
              {frame?.zone && (
                <span className="hidden rounded bg-black/55 px-2 py-1 text-xs font-semibold backdrop-blur-sm sm:inline">
                  {ZONE_NAMES[frame.zone]}
                </span>
              )}
            </div>
          </div>
          {/* Controles */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line px-4 py-2">
            <button
              type="button"
              onClick={toggle}
              aria-label={playing ? 'Pausar' : 'Reproducir'}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-bg transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <input
              type="range"
              min={0}
              max={race.video.duration}
              step={0.01}
              value={t}
              onChange={(e) => seek(Number(e.target.value))}
              aria-label="Línea de tiempo"
              className="min-w-40 flex-1 accent-accent"
            />
            <span className="font-mono text-xs whitespace-nowrap text-muted tabular-nums">
              {fmtSeconds(t)} / {fmtSeconds(race.video.duration)}
            </span>
            <div className="flex gap-4">
              <Toggle checked={overlay} onChange={setOverlay} label="Capa aumentada" />
              <Toggle checked={ghost} onChange={setGhost} label="Fantasma por la cuerda" />
            </div>
          </div>
        </section>

        <aside className="flex min-w-0 flex-col gap-4">
          {hasGeometry && selectedId !== undefined ? (
            <ResultCard race={race} selectedId={selectedId} series={selSeries} />
          ) : (
            <Pending title="Resultado de la curva">
              Cuando TRAZADA ubique a cada corredor en la pista (en metros), aquí aparece cuántos puestos ganó y
              cuántos metros extra corrió.
            </Pending>
          )}
          <Leaderboard race={race} frameIndex={fi} selectedId={selectedId} onSelect={setSelectedId} />
        </aside>
      </div>

      {/* Fila 2: el balance, a todo el ancho */}
      <section className="rounded-xl border border-line bg-panel p-6">
        {hasGeometry && selectedId !== undefined ? (
          <BalanceChart race={race} selectedId={selectedId} t={t} />
        ) : (
          <>
            <h2 className="font-display text-2xl leading-tight font-bold">Balance de adelantar</h2>
            <p className="mt-2 max-w-prose text-sm text-muted">
              Aquí se ve, para el corredor elegido, cuánto le sacó al grupo y cuánto le costó hacerlo por fuera. Falta
              ubicar a cada corredor en la pista; mientras tanto, míralo en el modo Simulación.
            </p>
          </>
        )}
      </section>

      {/* Fila 3: pista desde arriba + ficha del corredor */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section className="min-w-0 overflow-hidden rounded-xl border border-line bg-panel">
          <header className="flex items-baseline justify-between gap-4 px-6 pt-4">
            <h2 className="text-sm font-semibold">Vista cenital</h2>
            <p className="text-xs text-muted">pista de 400 m a escala</p>
          </header>
          <div className="relative">
            <TopView race={race} frameIndex={fi} showGhost={ghost} selectedId={selectedId} onSelect={setSelectedId} />
            {!hasGeometry && (
              <p className="absolute inset-x-0 bottom-4 mx-auto w-fit max-w-[90%] rounded-md bg-bg/85 px-3 py-1.5 text-center text-xs text-muted">
                Falta ubicar a cada corredor en la pista
              </p>
            )}
          </div>
        </section>

        {hasGeometry && selectedId !== undefined ? (
          <section className="min-w-0 rounded-xl border border-line bg-panel p-6">
            <header className="mb-4 flex items-baseline gap-3">
              <h2 className="text-sm font-semibold">Ficha del corredor</h2>
              <p className="font-display text-2xl leading-none font-bold">{selected?.label}</p>
            </header>
            <RunnerStats race={race} selectedId={selectedId} series={selSeries} />
            <div className="mt-4">
              <RunnerTelemetry series={series} runners={race.runners} selectedId={selectedId} currentS={currentS} />
            </div>
          </section>
        ) : (
          <Pending title="Ficha del corredor">
            Elige un corredor haciendo clic sobre él en el video. Con su ubicación en la pista, aquí se ve qué tan lejos
            de la cuerda corrió y dónde sumó metros extra.
          </Pending>
        )}
      </div>
    </div>
  )
}

function Pending({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-dashed border-line bg-panel/60 p-6">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="mt-2 text-sm text-muted">{children}</p>
    </section>
  )
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 text-xs text-muted select-none">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="accent-accent" />
      {label}
    </label>
  )
}

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
    <path d="M3 1.5v11l9-5.5z" fill="currentColor" />
  </svg>
)
const PauseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
    <path d="M3 1.5h3v11H3zM8 1.5h3v11H8z" fill="currentColor" />
  </svg>
)
