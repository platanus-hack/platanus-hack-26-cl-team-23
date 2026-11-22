import { useState } from 'react'
import { BarcodeScrubber } from '../components/trazada/BarcodeScrubber'
import { CameraView } from '../components/trazada/CameraView'
import { NarrationPanel } from '../components/trazada/NarrationPanel'
import { RunnerList, RunnerStats } from '../components/trazada/RunnerList'
import { TopViewZoom } from '../components/trazada/TopViewZoom'
import { UploadPanel } from '../components/trazada/UploadPanel'
import { Button, Figure, PageTitle, Pending } from '../components/trazada/ui'
import { NavActions } from '../navActions'
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
      <div className="flex flex-col gap-10">
        <PageTitle
          title="Mira la carrera que el cronómetro no ve."
          lede="Sube el video de una curva: TRAZADA sigue a cada corredor cuadro a cuadro y lo ubica en la pista."
        />
        <UploadPanel onReady={replace} />
      </div>
    )
  // key: al cambiar de video, la pantalla parte de cero (tiempo, corredor elegido…)
  return <RaceScreen key={race.video.url} race={race} onNewUpload={() => replace(null)} />
}

/** Título con valor: qué se midió y en cuántos metros de pista. */
function raceTitle(race: Race) {
  const n = race.runners.length
  const who = `${n} ${n === 1 ? 'corredor' : 'corredores'}`
  if (!race.camera) return `${who} seguidos en ${fmtNum(race.video.duration, 1)} s`
  const meters = Math.abs(race.camera.span[1] - race.camera.span[0])
  return `${who} en ${fmtNum(meters, 0)} m de pista`
}

function RaceScreen({ race, onNewUpload }: { race: Race; onNewUpload: () => void }) {
  const { t, playing, toggle, seek } = usePlayback(race.video.duration)
  const [overlay, setOverlay] = useState(true)
  const [selectedId, setSelectedId] = useState(race.defaultId ?? race.runners[0]?.id)
  const fi = frameAt(race.frames, t)
  const frame = race.frames[fi]
  const selected = race.runners.find((r) => r.id === selectedId)
  const zone = frame?.zone !== undefined ? (race.camera?.names[frame.zone] ?? `Zona ${frame.zone}`) : undefined

  // Atletas medidos en este cuadro: ritmo medio y cuántos metros separan al primero del último.
  const seenNow = (frame?.athletes ?? []).filter((a) => a.visible)
  const meanV = seenNow.reduce((sum, a) => sum + a.v, 0) / Math.max(1, seenNow.length)
  const spread = seenNow.length ? Math.max(...seenNow.map((a) => a.x)) - Math.min(...seenNow.map((a) => a.x)) : 0

  const mapTitle = race.hasAthletes ? 'Dónde está cada atleta' : 'Dónde mira la cámara'

  const facts = [
    race.title,
    race.pipeline ? `${race.pipeline.detector} + ${race.pipeline.tracker}` : undefined,
    `${fmtSeconds(race.video.duration)} · ${race.frames.length} cuadros`,
    race.hasAthletes && race.raw.zones
      ? `Prueba ${fmtNum(race.raw.zones.distance, 0)} m`
      : race.camera
        ? `Tramo ${fmtNum(race.camera.span[0], 0)}–${fmtNum(race.camera.span[1], 0)} m`
        : undefined,
  ].filter((f): f is string => !!f)

  return (
    <div className="flex flex-col gap-10">
      <NavActions>
        <Button onClick={onNewUpload}>Subir otro video</Button>
      </NavActions>

      <PageTitle title={raceTitle(race)} facts={facts} />
      {race.note && <Pending>{race.note}</Pending>}

      <div className="grid items-start gap-[var(--section-gap)] lg:grid-cols-[minmax(0,1fr)_340px]">
        <Figure title="Cámara" flush meta={`${frame?.runners.length ?? 0} en pantalla · ${fmtSeconds(t)}`}>
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
            {zone && (
              <span className="label glass pointer-events-none absolute top-3 right-3 rounded-ui px-2.5 py-1 text-fg">{zone}</span>
            )}
          </div>
          {/* Controles: la línea de tiempo es un código de barras de la carrera */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-6 py-4">
            <button
              type="button"
              onClick={toggle}
              aria-label={playing ? 'Pausar' : 'Reproducir'}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-fg text-white transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              {playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <BarcodeScrubber race={race} t={t} onSeek={seek} />
            <span className="label whitespace-nowrap text-muted">
              {fmtSeconds(t)} / {fmtSeconds(race.video.duration)}
            </span>
            <Toggle checked={overlay} onChange={setOverlay} label="Capa del detector" />
          </div>
        </Figure>

        <RunnerList race={race} frameIndex={fi} selectedId={selectedId} onSelect={setSelectedId} />
      </div>

      {/* key: al cambiar de video, el relato anterior se descarta sin efectos raros */}
      <NarrationPanel key={race.video.url} race={race} t={t} playing={playing} />

      <div className="grid gap-[var(--section-gap)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {race.camera && (
          <Figure title={mapTitle} flush meta="Pista de 400 m · carriles ensanchados">
            <TopViewZoom race={race} frameIndex={fi} selectedId={selectedId} title={mapTitle} />
            <dl className="grid grid-cols-3 gap-2 px-6 pt-2 pb-6">
              {race.hasAthletes ? (
                <>
                  <Stat term="Atletas medidos" value={`${seenNow.length} de ${race.runners.length}`} />
                  <Stat term="Ritmo del grupo" value={seenNow.length ? `${fmtNum(meanV, 1)} m/s` : '—'} />
                  <Stat term="Primero a último" value={seenNow.length > 1 ? `${fmtNum(spread, 0)} m` : '—'} />
                </>
              ) : (
                <>
                  <Stat term="Tramo enfocado" value={`${fmtNum(race.camera.span[0], 0)}–${fmtNum(race.camera.span[1], 0)} m`} />
                  <Stat term="Cambios de plano" value={`${race.camera.cuts.length}`} />
                  <Stat term="Barrido" value={frame?.focusV !== undefined ? `${fmtNum(frame.focusV, 1)} m/s` : '—'} />
                </>
              )}
            </dl>
          </Figure>
        )}

        {selected && (
          <Figure title="Ficha del corredor" meta={`${race.hasAthletes ? 'Atleta' : 'Corredor'} ${selected.label}`}>
            <RunnerStats race={race} selectedId={selected.id} frameIndex={fi} />
          </Figure>
        )}
      </div>
    </div>
  )
}

function Stat({ term, value }: { term: string; value: string }) {
  return (
    <div className="bento flex min-h-20 flex-col justify-between p-3">
      <dt className="label text-muted">{term}</dt>
      <dd className="text-xl font-semibold whitespace-nowrap">{value}</dd>
    </div>
  )
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-sm text-muted select-none">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
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
