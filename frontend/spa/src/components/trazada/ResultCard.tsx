import { averageSpeed, type SeriesPoint } from '../../trazada/analysis'
import { fmtMeters, fmtNum, fmtSeconds } from '../../trazada/format'
import { visibleAt } from '../../trazada/adapter'
import type { Race, RunnerResult, RunnerSample } from '../../trazada/types'

const plural = (n: number) => (Math.abs(n) === 1 ? 'puesto' : 'puestos')

function headlineFor(res: RunnerResult) {
  const gained = res.startRank - res.endRank
  if (gained > 0) return `Ganó ${gained} ${plural(gained)}${res.extraM > 1 ? ' por fuera' : ''}`
  if (gained === 0) return 'Mantuvo su puesto'
  return `Perdió ${-gained} ${plural(gained)}`
}

/** Titular del corredor elegido: lo primero que lee el entrenador. */
export function ResultCard({ race, selectedId, series }: { race: Race; selectedId: number; series?: SeriesPoint[] }) {
  const runner = race.runners.find((r) => r.id === selectedId)
  const res = race.results.find((r) => r.id === selectedId)
  if (!runner || !res) return null
  const speed = averageSpeed(series)
  const cost = speed ? res.extraM / speed : undefined

  return (
    <div className="rounded-xl border border-line bg-panel px-6 py-5">
      <h2 className="text-sm font-semibold text-muted">Resultado de la curva</h2>
      <p className="mt-2 font-display text-[40px] leading-[.95] font-extrabold text-balance uppercase">
        {headlineFor(res)}
      </p>
      <p className="mt-1 font-display text-[64px] leading-none font-extrabold text-pick tabular-nums">
        {fmtMeters(res.extraM)}
      </p>
      <p className="mt-3 text-sm text-muted">
        <b className="font-semibold text-fg">{runner.label}</b> pasó del {res.startRank}.º al {res.endRank}.º lugar
        {cost !== undefined && (
          <>
            . Esos metros extra le costaron <b className="font-mono font-medium text-fg">≈ {fmtSeconds(cost, 2)}</b>
          </>
        )}
      </p>
    </div>
  )
}

/** Tabla en vivo: puesto y metros extra al tiempo actual. Clic en una fila para elegir corredor. */
export function Leaderboard({
  race,
  frameIndex,
  selectedId,
  onSelect,
}: {
  race: Race
  frameIndex: number
  selectedId: number | undefined
  onSelect: (id: number) => void
}) {
  const frame = race.frames[frameIndex]
  if (!frame) return null
  const info = new Map(race.runners.map((r) => [r.id, r]))
  // Con geometría: ordenados por quién va adelante.
  // Sin ella: lista ESTABLE de los corredores que están en carrera ahora (por ID), para que
  // las filas no aparezcan y desaparezcan cada vez que el detector pierde a alguien un instante.
  const hasS = frame.runners.some((r) => r.s !== undefined)
  // Igual que en el video: un corredor perdido menos de 0,5 s sigue "visto" (si no, la fila titila).
  const seen = new Map(visibleAt(race.frames, frameIndex).map((r) => [r.id, r]))
  const rows = hasS
    ? [...frame.runners].filter((r) => r.s !== undefined).sort((a, b) => b.s! - a.s!)
    : race.runners
        .filter((r) => (r.tStart ?? 0) <= frame.t && frame.t <= (r.tEnd ?? Infinity))
        .sort((a, b) => a.id - b.id)
        .map((r): RunnerSample => seen.get(r.id) ?? { id: r.id })
  const start = new Map(race.results.map((r) => [r.id, r.startRank]))
  return (
    <div className="flex-1 rounded-xl border border-line bg-panel py-3">
      <div className="mb-1 flex items-baseline justify-between px-5">
        <h2 className="text-sm font-semibold">Posiciones</h2>
        <p className="text-xs text-muted">{hasS ? 'metros extra' : `${rows.length} en carrera`}</p>
      </div>
      <ol className="max-h-72 overflow-y-auto">
        {rows.map((r, i) => {
          const isSel = r.id === selectedId
          const delta = (start.get(r.id) ?? i + 1) - (i + 1)
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
                <span className="w-4 font-display text-lg leading-none font-bold text-muted tabular-nums">{hasS ? i + 1 : ''}</span>
                <span className={`font-display text-xl leading-none font-bold tracking-wide ${isSel ? 'text-fg' : 'text-fg/75'}`}>
                  {info.get(r.id)?.label}
                </span>
                <span className="w-6 font-mono text-[11px] text-muted tabular-nums">
                  {hasS && delta > 0 ? `▲${delta}` : hasS && delta < 0 ? `▼${-delta}` : ''}
                </span>
                <span className={`ml-auto font-mono text-sm tabular-nums ${isSel ? 'font-bold text-hero' : 'text-muted'}`}>
                  {r.extraM !== undefined ? fmtMeters(r.extraM) : '—'}
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

/** Cifras clave del corredor elegido. */
export function RunnerStats({ race, selectedId, series }: { race: Race; selectedId: number; series?: SeriesPoint[] }) {
  const res = race.results.find((r) => r.id === selectedId)
  if (!res || !series?.length) return null
  const speed = averageSpeed(series)
  const maxD = Math.max(...series.map((p) => p.d))
  const gained = res.startRank - res.endRank
  const stats = [
    { label: 'Metros extra', value: fmtMeters(res.extraM) },
    { label: 'Tiempo que costaron', value: speed ? `${fmtNum(res.extraM / speed, 2)} s` : '—' },
    { label: 'Puestos', value: gained > 0 ? `+${gained}` : `${gained}` },
    { label: 'Máx. lejos de la cuerda', value: `${fmtNum(maxD, 1)} m` },
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
