import { useState } from 'react'
import { CameraView } from '../components/trazada/CameraView'
import { RunnerList, RunnerStats } from '../components/trazada/RunnerList'
import { UploadPanel } from '../components/trazada/UploadPanel'
import { TopView } from '../components/trazada/TopView'
import { frameAt } from '../trazada/adapter'
import { fmtNum, fmtSeconds } from '../trazada/format'
import type { Race } from '../trazada/types'
import { usePlayback } from '../trazada/usePlayback'

/** Pantalla principal de TRAZADA: subir un video y ver lo que el backend encontró en él. */
export default function Home() {
  // La carrera vive solo en memoria: sale de procesar el video del usuario contra la API.
  const [race, setRace] = useState<Race | null>(null)
  const replace = (next: Race | null) => {
    if (race?.video.url?.startsWith('blob:')) URL.revokeObjectURL(race.video.url)
    setRace(next)
  }

  if (!race)
    return (
      <div className="flex flex-col gap-6">
        <Header title="Analiza tu carrera" subtitle="Sube el video de una curva y TRAZADA sigue a cada corredor." />
        <UploadPanel onReady={replace} />
      </div>
    )
  // key: al cambiar de video, la pantalla parte de cero (tiempo, corredor elegido…)
  return <RaceScreen key={race.video.url} race={race} onNewUpload={() => replace(null)} />
}

function Header({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="font-display text-[32px] leading-none font-extrabold">{title}</h1>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
      </div>
      {action && <div className="ml-auto flex flex-wrap items-center gap-3">{action}</div>}
    </div>
  )
}

function RaceScreen({ race, onNewUpload }: { race: Race; onNewUpload: () => void }) {
  const { t, playing, toggle, seek } = usePlayback(race.video.duration)
  const [overlay, setOverlay] = useState(true)
  const [selectedId, setSelectedId] = useState(race.defaultId ?? race.runners[0]?.id)
  const fi = frameAt(race.frames, t)
  const frame = race.frames[fi]
  const selected = race.runners.find((r) => r.id === selectedId)

  return (
    <div className="flex flex-col gap-6">
      <Header
        title={race.title}
        subtitle={
          race.note ??
          `${race.runners.length} corredores seguidos con ${race.pipeline?.detector ?? 'el detector'} + ${
            race.pipeline?.tracker ?? 'el tracker'
          }`
        }
        action={
          <button
            type="button"
            onClick={onNewUpload}
            className="min-h-9 rounded-md border border-line px-3 text-sm font-semibold text-fg hover:border-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Subir otro video
          </button>
        }
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="min-w-0 overflow-hidden rounded-xl border border-line bg-panel">
          <div className="relative">
            <CameraView
              race={race}
              frameIndex={fi}
              t={t}
              playing={playing}
              showOverlay={overlay}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
            {/* HUD tipo transmisión */}
            <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-4">
              <span className="flex items-center gap-2 rounded bg-black/55 px-2 py-1 text-xs font-semibold backdrop-blur-sm">
                <span className="h-2 w-2 rounded-full bg-red-500" />
                <span className="font-mono text-fg/80 tabular-nums">{fmtSeconds(t)}</span>
                <span className="text-fg/80">· {frame?.runners.length ?? 0} en pantalla</span>
              </span>
              {frame?.zone !== undefined && (
                <span className="hidden rounded bg-black/55 px-2 py-1 text-xs font-semibold backdrop-blur-sm sm:inline">
                  {race.camera?.names[frame.zone] ?? `Zona ${frame.zone}`}
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
            <Toggle checked={overlay} onChange={setOverlay} label="Capa del detector" />
          </div>
        </section>

        <aside className="flex min-w-0 flex-col gap-4">
          <RunnerList race={race} frameIndex={fi} selectedId={selectedId} onSelect={setSelectedId} />
        </aside>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {race.camera && (
          <section className="min-w-0 overflow-hidden rounded-xl border border-line bg-panel">
            <header className="flex items-baseline justify-between gap-4 px-6 pt-4">
              <h2 className="text-sm font-semibold">Dónde mira la cámara</h2>
              <p className="text-xs text-muted">pista de 400 m a escala</p>
            </header>
            <TopView race={race} frameIndex={fi} />
            <dl className="flex flex-wrap gap-x-6 gap-y-1 px-6 pb-4 text-xs text-muted">
              <div className="flex gap-1.5">
                <dt>Tramo enfocado:</dt>
                <dd className="font-mono text-fg tabular-nums">
                  {fmtNum(race.camera.span[0], 0)}–{fmtNum(race.camera.span[1], 0)} m
                </dd>
              </div>
              <div className="flex gap-1.5">
                <dt>Cambios de plano:</dt>
                <dd className="font-mono text-fg tabular-nums">{race.camera.cuts.length}</dd>
              </div>
              {frame?.focusV !== undefined && (
                <div className="flex gap-1.5">
                  <dt>Barrido:</dt>
                  <dd className="font-mono text-fg tabular-nums">{fmtNum(frame.focusV, 1)} m/s</dd>
                </div>
              )}
            </dl>
          </section>
        )}

        {selected && (
          <section className="min-w-0 rounded-xl border border-line bg-panel p-6">
            <header className="mb-4 flex items-baseline gap-3">
              <h2 className="text-sm font-semibold">Ficha del corredor</h2>
              <p className="font-display text-2xl leading-none font-bold">{selected.label}</p>
            </header>
            <RunnerStats race={race} selectedId={selected.id} />
          </section>
        )}
      </div>
    </div>
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
