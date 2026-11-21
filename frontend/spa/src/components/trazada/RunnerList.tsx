import type { ReactNode } from 'react'
import { visibleAt } from '../../trazada/adapter'
import { fmtNum, fmtSeconds } from '../../trazada/format'
import type { AthleteSample, Race } from '../../trazada/types'
import { useTween } from '../../trazada/useTween'
import { Figure } from './ui'

type Props = {
  race: Race
  frameIndex: number
  selectedId: number | undefined
  onSelect: (id: number) => void
}

/**
 * Corredores que el tracker siguió. Sin metros no hay puestos: la lista va por id, estable,
 * y se atenúan los que no están en pantalla en este instante.
 * Color: naranja solo para el elegido; el resto en grises.
 */
export function RunnerList({ race, frameIndex, selectedId, onSelect }: Props) {
  const frame = race.frames[frameIndex]
  if (!frame) return null
  // Igual que en el video: a quien se perdió hace menos de 0,5 s se le sigue considerando visto.
  const seen = new Set(visibleAt(race.frames, frameIndex).map((r) => r.rid))
  const inRace = race.runners.filter((r) => r.tStart <= frame.t && frame.t <= r.tEnd)
  // Con atletas hay puestos: la lista va por puesto actual; los que aún no se miden, al final.
  const live = new Map((frame.athletes ?? []).map((a) => [a.id, a]))
  const ordered = race.hasAthletes
    ? [...race.runners].sort((a, b) => (live.get(a.id)?.rank ?? 99) - (live.get(b.id)?.rank ?? 99) || a.id - b.id)
    : race.runners

  return (
    <Figure title={race.hasAthletes ? 'Atletas' : 'Corredores'} meta={`${inRace.length} de ${race.runners.length} en carrera`}>
      {race.runners.length === 0 ? (
        <p className="text-sm text-muted">El detector no encontró corredores en este video.</p>
      ) : (
        <ol className="-mx-2 max-h-96 overflow-y-auto">
          {ordered.map((r) => {
            const isSel = r.id === selectedId
            const now = live.get(r.id)
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onSelect(r.id)}
                  aria-pressed={isSel}
                  className={`flex min-h-11 w-full items-center gap-3 rounded-inner px-2 text-left transition-colors ${
                    isSel ? 'bg-band' : 'hover:bg-paper2'
                  } ${seen.has(r.id) ? '' : 'opacity-40'} focus-visible:outline-2 focus-visible:-outline-offset-2`}
                >
                  {now && <span className="label w-5 shrink-0 text-muted tabular-nums">{now.rank}</span>}
                  <span className="min-w-0 truncate text-xl leading-none font-semibold tracking-[-0.01em]">{r.label}</span>
                  <span className={`label ml-auto whitespace-nowrap tabular-nums ${isSel ? 'text-hero' : 'text-muted'}`}>
                    {now?.visible ? `${fmtNum(now.v, 1)} m/s` : fmtSeconds(r.tEnd - r.tStart)}
                  </span>
                  <TrackGauge value={r.onTrack} selected={isSel} />
                </button>
              </li>
            )
          })}
        </ol>
      )}
      <p className="label mt-3 text-muted">
        {race.hasAthletes
          ? 'Por puesto · velocidad respecto a la cancha · barra: pisando la pista'
          : 'Tiempo en pantalla · barra: pisando la pista'}
      </p>
    </Figure>
  )
}

/** Medidor vertical mini: fracción del tiempo que el corredor iba pisando la pista (0 a 1). */
function TrackGauge({ value, selected }: { value: number; selected: boolean }) {
  const k = Math.min(1, Math.max(0, value))
  return (
    <span
      aria-hidden="true"
      className={`relative h-7 w-1.5 shrink-0 rounded-full ${
        selected
          ? 'bg-[linear-gradient(to_top,var(--color-band),var(--color-pick))]'
          : 'bg-[linear-gradient(to_top,var(--color-line),var(--color-other))]'
      }`}
    >
      <span
        className="absolute -inset-x-1 bottom-0 h-0.5 rounded-full bg-fg transition-transform duration-300 ease-[var(--ease-out)]"
        style={{ transform: `translateY(${-k * 26}px)` }}
      />
    </span>
  )
}

/** Última medición de un atleta: la del cuadro actual o, si no se ve, la más reciente de hace < 3 s. */
function latestSample(race: Race, frameIndex: number, id: number): { sample: AthleteSample; stale: boolean } | undefined {
  const t = race.frames[frameIndex]?.t ?? 0
  for (let i = frameIndex; i >= 0 && t - race.frames[i].t <= 3; i--) {
    const sample = race.frames[i].athletes?.find((a) => a.id === id)
    if (sample) return { sample, stale: i !== frameIndex || !sample.visible }
  }
  return undefined
}

/** Puestos ganados (+) o perdidos (−) entre la primera y la última medición. */
function RankDelta({ start, end }: { start: number; end: number }) {
  const gained = start - end
  if (gained === 0) return <span>=</span>
  return (
    <span className={gained > 0 ? 'text-gain' : 'text-loss'}>
      {gained > 0 ? '▲' : '▼'} {Math.abs(gained)}
    </span>
  )
}

/**
 * Ficha del corredor elegido. Con atletas: velocidad, puesto, calle y metros extra por ir por
 * fuera; sin ellos, solo lo que el tracker sabe. La cifra principal del tracker rueda.
 */
export function RunnerStats({ race, selectedId, frameIndex }: { race: Race; selectedId: number; frameIndex: number }) {
  const runner = race.runners.find((r) => r.id === selectedId)
  const shown = useTween(runner ? runner.tEnd - runner.tStart : 0)
  if (!runner) return null

  const summary = runner.summary
  if (race.hasAthletes && summary) {
    const last = latestSample(race, frameIndex, runner.id)
    const now = last?.sample
    const tiles: { label: string; value: ReactNode }[] = [
      { label: 'Puesto', value: now ? `${now.rank}.º` : '—' },
      { label: 'Puestos', value: <RankDelta start={summary.startRank} end={summary.endRank} /> },
      { label: 'Vel. media', value: `${fmtNum(summary.avgV, 1)} m/s` },
      { label: 'Vel. máxima', value: `${fmtNum(summary.maxV, 1)} m/s` },
      { label: 'Calle', value: now ? `${now.lane}` : '—' },
      { label: 'Al bordillo', value: now ? `${fmtNum(now.d, 1)} m` : '—' },
      { label: 'Recorrido', value: `${fmtNum(summary.meters, 0)} m` },
      { label: 'Metros extra', value: `+${fmtNum(summary.extraM, 1)} m` },
    ]
    return (
      <div>
        <p className="hero-number" aria-hidden="true">
          {now ? fmtNum(now.v, 1) : '—'}
          <span className="ml-2 text-xl font-semibold text-muted">m/s</span>
        </p>
        <p className="sr-only" aria-live="polite">
          {now ? `${fmtNum(now.v, 1)} metros por segundo` : 'sin medición en este instante'}
        </p>
        <p className="mt-3 text-sm text-muted">
          {last?.stale
            ? 'última velocidad medida: ahora no se le ve'
            : 'velocidad respecto a la cancha, en este instante'}
          {now && ` · ± ${fmtNum(now.sigmaX, 1)} m de precisión`}
        </p>
        <dl className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {tiles.map((s) => (
            <div key={s.label} className="bento flex min-h-20 flex-col justify-between p-3">
              <dt className="label text-muted">{s.label}</dt>
              <dd className="stat-number whitespace-nowrap">{s.value}</dd>
            </div>
          ))}
        </dl>
        <p className="label mt-3 text-muted">
          Metros extra: lo que corre de más por ir por fuera de la calle 1 en las curvas (estimado) ·{' '}
          {fmtSeconds(runner.tEnd - runner.tStart)} en pantalla
        </p>
      </div>
    )
  }

  const stats = [
    { label: 'Aparece en', value: fmtSeconds(runner.tStart) },
    { label: 'Se le pierde en', value: fmtSeconds(runner.tEnd) },
    { label: 'Cuadros seguidos', value: `${runner.nObs}` },
    { label: 'Pisando la pista', value: `${fmtNum(runner.onTrack * 100, 0)} %` },
  ]
  return (
    <div>
      <p className="hero-number" aria-hidden="true">
        {fmtSeconds(shown)}
      </p>
      <p className="sr-only" aria-live="polite">
        {fmtSeconds(runner.tEnd - runner.tStart)} en pantalla
      </p>
      <p className="mt-3 text-sm text-muted">seguido por el detector, de principio a fin</p>
      <dl className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="bento flex min-h-20 flex-col justify-between p-3">
            <dt className="label text-muted">{s.label}</dt>
            <dd className="stat-number whitespace-nowrap">{s.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
