import { visibleAt } from '../../trazada/adapter'
import { fmtNum, fmtSeconds } from '../../trazada/format'
import type { Race } from '../../trazada/types'
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
  const seen = new Set(visibleAt(race.frames, frameIndex).map((r) => r.id))
  const inRace = race.runners.filter((r) => r.tStart <= frame.t && frame.t <= r.tEnd)

  return (
    <Figure title="Corredores" meta={`${inRace.length} de ${race.runners.length} en carrera`}>
      {race.runners.length === 0 ? (
        <p className="text-sm text-muted">El detector no encontró corredores en este video.</p>
      ) : (
        <ol className="-mx-2 max-h-96 overflow-y-auto">
          {race.runners.map((r) => {
            const isSel = r.id === selectedId
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
                  <span className="min-w-0 truncate text-xl leading-none font-semibold tracking-[-0.01em]">{r.label}</span>
                  <span className={`label ml-auto whitespace-nowrap ${isSel ? 'text-hero' : 'text-muted'}`}>
                    {fmtSeconds(r.tEnd - r.tStart)}
                  </span>
                  <TrackGauge value={r.onTrack} selected={isSel} />
                </button>
              </li>
            )
          })}
        </ol>
      )}
      <p className="label mt-3 text-muted">Tiempo en pantalla · barra: pisando la pista</p>
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

/** Ficha del corredor elegido: solo lo que el tracker sabe de él. La cifra principal rueda. */
export function RunnerStats({ race, selectedId }: { race: Race; selectedId: number }) {
  const runner = race.runners.find((r) => r.id === selectedId)
  const shown = useTween(runner ? runner.tEnd - runner.tStart : 0)
  if (!runner) return null
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
