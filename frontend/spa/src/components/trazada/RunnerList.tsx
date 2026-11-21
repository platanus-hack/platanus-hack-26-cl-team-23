import { visibleAt } from '../../trazada/adapter'
import { fmtNum, fmtSeconds } from '../../trazada/format'
import type { Race } from '../../trazada/types'

type Props = {
  race: Race
  frameIndex: number
  selectedId: number | undefined
  onSelect: (id: number) => void
}

/**
 * Corredores que el tracker siguió. Sin metros no hay puestos: la lista va por id, estable,
 * y se atenúan los que no están en pantalla en este instante.
 */
export function RunnerList({ race, frameIndex, selectedId, onSelect }: Props) {
  const frame = race.frames[frameIndex]
  if (!frame) return null
  // Igual que en el video: a quien se perdió hace menos de 0,5 s se le sigue considerando visto.
  const seen = new Set(visibleAt(race.frames, frameIndex).map((r) => r.id))
  const inRace = race.runners.filter((r) => r.tStart <= frame.t && frame.t <= r.tEnd)

  return (
    <div className="flex-1 rounded-xl border border-line bg-panel py-3">
      <div className="mb-1 flex items-baseline justify-between px-5">
        <h2 className="text-sm font-semibold">Corredores seguidos</h2>
        <p className="text-xs text-muted">
          {inRace.length} de {race.runners.length}
        </p>
      </div>
      <ol className="max-h-72 overflow-y-auto">
        {race.runners.map((r) => {
          const isSel = r.id === selectedId
          return (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onSelect(r.id)}
                aria-pressed={isSel}
                className={`flex min-h-10 w-full items-center gap-3 px-5 text-left transition-colors ${
                  isSel ? 'bg-pick/10' : 'hover:bg-white/5'
                } ${seen.has(r.id) ? '' : 'opacity-40'} focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent`}
              >
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: r.color }} />
                <span
                  className={`font-display text-xl leading-none font-bold tracking-wide ${isSel ? 'text-fg' : 'text-fg/75'}`}
                >
                  {r.label}
                </span>
                <span className="ml-auto font-mono text-xs text-muted tabular-nums">
                  {fmtSeconds(r.tEnd - r.tStart)} en pantalla
                </span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="mt-2 px-5 text-xs text-muted">Elige un corredor aquí o haciendo clic sobre él.</p>
    </div>
  )
}

/** Ficha del corredor elegido: solo lo que el tracker sabe de él. */
export function RunnerStats({ race, selectedId }: { race: Race; selectedId: number }) {
  const runner = race.runners.find((r) => r.id === selectedId)
  if (!runner) return null
  const stats = [
    { label: 'Aparece en', value: fmtSeconds(runner.tStart) },
    { label: 'Se le pierde en', value: fmtSeconds(runner.tEnd) },
    { label: 'Cuadros seguidos', value: `${runner.nObs}` },
    { label: 'Pisando la pista', value: `${fmtNum(runner.onTrack * 100, 0)} %` },
  ]
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="bg-panel px-3 py-2.5">
          <dt className="text-xs text-muted">{s.label}</dt>
          <dd className="font-display text-[28px] leading-tight font-bold tabular-nums">{s.value}</dd>
        </div>
      ))}
    </dl>
  )
}
