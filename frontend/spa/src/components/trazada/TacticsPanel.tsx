import { useMemo, type ReactNode } from 'react'
import { fmtClock, fmtNum, fmtPct } from '../../trazada/format'
import { remainingSegments, stepAt, useTactics } from '../../trazada/tactics'
import type { Attack, ForecastAthlete, Race, TacticsStep } from '../../trazada/types'
import { useTween } from '../../trazada/useTween'
import { Figure, Pending } from './ui'

type Props = {
  race: Race
  /** Reloj del video: el pronóstico que se ve es el calculado hasta ese instante. */
  t: number
  selectedId: number | undefined
  onSelect: (id: number) => void
}

const ease = 'transition-[width,left] duration-500 ease-[var(--ease-out)]'

/**
 * Pronóstico del final y mejores momentos para adelantar. Sale de un modelo (no de una
 * medición) que parte de lo que ya midió el módulo de atletas, y va al ritmo del video: lo que se
 * ve es lo que se podía pronosticar hasta ese instante. Naranja solo para el atleta elegido.
 */
export function TacticsPanel({ race, t, selectedId, onSelect }: Props) {
  const state = useTactics(race)
  if (state.kind === 'idle' || state.kind === 'error') return null

  if (state.kind === 'loading') {
    return (
      <Figure title="Pronóstico del final" meta="Calculando…">
        <Pending>Estimando quién llega primero y cuándo conviene adelantar, con lo que ya se midió.</Pending>
      </Figure>
    )
  }

  const { steps, disclaimer } = state.result
  const step = stepAt(steps, t)
  if (!step) {
    return (
      <Figure title="Pronóstico del final">
        <Pending>Aún no hay suficientes atletas medidos para pronosticar el final.</Pending>
      </Figure>
    )
  }

  return (
    <div className="grid items-start gap-[var(--section-gap)] lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <Forecast steps={steps} step={step} t={t} selectedId={selectedId} onSelect={onSelect} note={disclaimer} />
      {/* En pantalla ancha esta columna no decide el alto de la fila (lo decide el pronóstico):
          las tarjetas aparecen y desaparecen con el video, y así la página no salta. */}
      <div className="lg:relative lg:self-stretch">
        <Overtakes race={race} step={step} selectedId={selectedId} onSelect={onSelect} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Pronóstico del final
// ---------------------------------------------------------------------------------------------

function Forecast({
  steps,
  step,
  t,
  selectedId,
  onSelect,
  note,
}: {
  steps: TacticsStep[]
  step: TacticsStep
  t: number
  selectedId: number | undefined
  onSelect: (id: number) => void
  note: string
}) {
  const winner = step.winner
  const shown = useTween(winner?.[1] ?? 0)
  const lo = Math.min(...step.athletes.map((a) => a.eta[0]))
  const hi = Math.max(...step.athletes.map((a) => a.eta[2]))

  return (
    <Figure title="Pronóstico del final" meta="Modelo · se actualiza cada segundo">
      {winner && (
        <div>
          <p className="lead-number" aria-hidden="true">
            {fmtClock(shown)}
          </p>
          <p className="sr-only" aria-live="polite">
            Tiempo ganador estimado {fmtClock(winner[1])}
          </p>
          <p className="mt-2 text-sm text-muted">
            tiempo ganador estimado, desde el disparo · entre {fmtClock(winner[0])} y {fmtClock(winner[2])}
          </p>
        </div>
      )}

      <div className="mt-6">
        <div className="label grid grid-cols-[1.25rem_3rem_minmax(0,1fr)_5rem_minmax(0,8rem)_3.75rem] items-end gap-x-3 px-2 pb-2 text-muted max-sm:grid-cols-[1.25rem_3rem_minmax(0,1fr)_5rem_3.75rem]">
          <span />
          <span>Atleta</span>
          <span className="truncate max-sm:invisible">Opción de ganar · de podio</span>
          <span />
          <span className="max-sm:hidden">Llegada (10–90 %)</span>
          <span className="text-right">Mediana</span>
        </div>
        <ol className="-mx-0">
          {step.athletes.map((a, i) => (
            <ForecastRow
              key={a.id}
              a={a}
              place={i + 1}
              selected={a.id === selectedId}
              onSelect={onSelect}
              axis={[lo, hi]}
              labeled={i === 0}
            />
          ))}
        </ol>
      </div>

      <div className="mt-8">
        <div className="flex items-baseline justify-between">
          <h3 className="title">Cómo cambia la opción de ganar</h3>
          <span className="label text-muted">P(gana) en el tiempo</span>
        </div>
        <WinChart steps={steps} t={t} selectedId={selectedId} />
      </div>

      <p className="label mt-6 text-muted">{note}</p>
    </Figure>
  )
}

function ForecastRow({
  a,
  place,
  selected,
  onSelect,
  axis,
  labeled,
}: {
  a: ForecastAthlete
  place: number
  selected: boolean
  onSelect: (id: number) => void
  axis: [number, number]
  /** La primera fila dice qué es cada número; las demás lo heredan por posición. */
  labeled: boolean
}) {
  const span = Math.max(1e-6, axis[1] - axis[0])
  const left = ((a.eta[0] - axis[0]) / span) * 100
  const width = Math.max(1.5, ((a.eta[2] - a.eta[0]) / span) * 100)
  const mid = ((a.eta[1] - axis[0]) / span) * 100
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(a.id)}
        aria-pressed={selected}
        className={`grid min-h-12 w-full grid-cols-[1.25rem_3rem_minmax(0,1fr)_5rem_minmax(0,8rem)_3.75rem] items-center gap-x-3 rounded-inner px-2 text-left transition-colors max-sm:grid-cols-[1.25rem_3rem_minmax(0,1fr)_5rem_3.75rem] ${
          selected ? 'bg-band' : 'hover:bg-paper2'
        } focus-visible:outline-2 focus-visible:-outline-offset-2`}
      >
        <span className="label text-muted tabular-nums">{place}</span>
        <span className="truncate text-xl leading-none font-semibold tracking-[-0.01em]">#{a.id}</span>

        {/* barra gruesa: P(gana); barra fina: P(podio) */}
        <span className="flex flex-col gap-1" aria-hidden="true">
          <span className="block h-2.5 rounded-full bg-line">
            <span
              className={`block h-full rounded-full ${selected ? 'bg-pick' : 'bg-fg'} ${ease}`}
              style={{ width: `${Math.max(a.p_win * 100, a.p_win > 0 ? 1.5 : 0)}%` }}
            />
          </span>
          <span className="block h-1 rounded-full bg-line">
            <span className={`block h-full rounded-full bg-other ${ease}`} style={{ width: `${a.p_podium * 100}%` }} />
          </span>
        </span>
        <span className="grid grid-cols-[auto_1fr] items-baseline gap-x-1.5 leading-tight">
          <span className="label text-muted" aria-hidden="true">{labeled ? 'gana' : ''}</span>
          <span className={`text-right text-sm font-semibold tabular-nums ${selected ? 'text-hero' : ''}`}>
            <span className="sr-only">gana </span>
            {fmtPct(a.p_win)}
          </span>
          <span className="label text-muted" aria-hidden="true">{labeled ? 'podio' : ''}</span>
          <span className="text-right text-xs text-muted tabular-nums">
            <span className="sr-only">podio </span>
            {fmtPct(a.p_podium)}
          </span>
        </span>

        <span className="relative h-1.5 rounded-full bg-line max-sm:hidden" aria-hidden="true">
          <span
            className={`absolute inset-y-0 rounded-full ${selected ? 'bg-pick' : 'bg-other'} ${ease}`}
            style={{ left: `${left}%`, width: `${width}%` }}
          />
          <span
            className={`absolute -top-1 h-3.5 w-0.5 rounded-full bg-fg ${ease}`}
            style={{ left: `${mid}%` }}
          />
        </span>
        <span className={`label text-right whitespace-nowrap tabular-nums ${selected ? 'text-hero' : 'text-muted'}`}>
          {fmtClock(a.eta[1])}
        </span>
      </button>
    </li>
  )
}

/** Líneas de P(gana) de cada atleta a lo largo del clip; el elegido en naranja, con la cabeza lectora. */
function WinChart({ steps, t, selectedId }: { steps: TacticsStep[]; t: number; selectedId: number | undefined }) {
  const t0 = steps[0].t
  const t1 = steps[steps.length - 1].t
  const span = Math.max(1e-6, t1 - t0)
  const x = (time: number) => ((time - t0) / span) * 100

  // Las líneas no dependen del reloj: se calculan una vez y no en cada cuadro del video.
  const { top, ordered } = useMemo(() => {
    const ids = [...new Set(steps.flatMap((s) => s.athletes.map((a) => a.id)))]
    const peak = Math.max(0.2, ...steps.flatMap((s) => s.athletes.map((a) => a.p_win)))
    const ceiling = Math.min(1, Math.ceil(peak * 4 + 0.001) / 4) // techo en cuartos: 25 %, 50 %…
    const series = ids.map((id) => ({
      id,
      points: steps.flatMap((s) => {
        const a = s.athletes.find((q) => q.id === id)
        return a ? [{ x: ((s.t - t0) / span) * 100, y: 100 - (a.p_win / ceiling) * 100 }] : []
      }),
    }))
    return {
      top: ceiling,
      ordered: [...series.filter((s) => s.id !== selectedId), ...series.filter((s) => s.id === selectedId)],
    }
  }, [steps, selectedId, t0, span])
  const y = (p: number) => 100 - (p / top) * 100
  const now = Math.min(100, Math.max(0, x(t)))
  const here = stepAt(steps, t)?.athletes.find((a) => a.id === selectedId)

  return (
    <div className="mt-3">
      <div className="relative h-36 rounded-inner bg-paper2">
        {[0.25, 0.5, 0.75].map((k) => (
          <span key={k} className="absolute inset-x-0 border-t border-line" style={{ top: `${k * 100}%` }} />
        ))}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden="true">
          {ordered.map((s) => {
            const sel = s.id === selectedId
            return (
              <polyline
                key={s.id}
                fill="none"
                points={s.points.map((p) => `${p.x},${p.y}`).join(' ')}
                stroke={sel ? 'var(--color-pick)' : 'var(--color-other)'}
                strokeWidth={sel ? 3 : 1.25}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={sel ? 1 : 0.65}
                vectorEffect="non-scaling-stroke"
              />
            )
          })}
        </svg>
        <span className="absolute inset-y-0 w-px bg-fg" style={{ left: `${now}%` }} aria-hidden="true" />
        {here && (
          <span
            className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-pick ring-2 ring-surface"
            style={{ left: `${now}%`, top: `${y(here.p_win)}%` }}
            aria-hidden="true"
          />
        )}
        <span className="label absolute top-1.5 left-2 text-muted">{fmtPct(top)}</span>
        <span className="label absolute bottom-1.5 left-2 text-muted">0 %</span>
      </div>
      <div className="label mt-1.5 flex justify-between text-muted">
        <span>{fmtNum(t0, 0)} s</span>
        <span>{fmtNum(t1, 0)} s</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// ¿Cuándo adelantar?
// ---------------------------------------------------------------------------------------------

function Overtakes({
  race,
  step,
  selectedId,
  onSelect,
}: {
  race: Race
  step: TacticsStep
  selectedId: number | undefined
  onSelect: (id: number) => void
}) {
  return (
    <Figure
      title="¿Cuándo adelantar?"
      meta="Mejores oportunidades ahora"
      className="lg:absolute lg:inset-0 lg:flex lg:flex-col"
      bodyClassName="lg:min-h-0 lg:flex-1 lg:overflow-y-auto"
    >
      {step.attacks.length === 0 ? (
        <Pending>En este momento no hay dos atletas medidos a menos de 15 m uno del otro.</Pending>
      ) : (
        <ul className="flex flex-col gap-3">
          {step.attacks.map((a) => (
            <li key={`${a.id}-${a.rival}`}>
              <AttackCard race={race} a={a} selected={a.id === selectedId} onSelect={onSelect} />
            </li>
          ))}
        </ul>
      )}
      <p className="label mt-4 text-muted">
        Probabilidad de pasar según dónde ataque · franja: dónde conviene · curvas más oscuras
      </p>
    </Figure>
  )
}

const ACTION: Record<Attack['action'], { chip: string; tone: string }> = {
  attack: { chip: 'Atacar ya', tone: 'bg-fg text-bg' },
  wait: { chip: 'Esperar', tone: 'bg-surface text-fg' },
  hold: { chip: 'Seguir a rebufo', tone: 'bg-surface text-muted' },
}

function AttackCard({
  race,
  a,
  selected,
  onSelect,
}: {
  race: Race
  a: Attack
  selected: boolean
  onSelect: (id: number) => void
}) {
  const zone = race.camera?.names[a.zone] ?? `zona ${a.zone}`
  const detail =
    a.action === 'attack'
      ? `de pasar al #${a.rival} si ataca ahora`
      : a.action === 'wait'
        ? `de pasarlo si espera a la ${zone} (a ${fmtNum(a.at_m, 0)} m de meta) · ahora solo ${fmtPct(a.p_now)}`
        : `en el mejor punto (${zone}): no alcanza, conviene seguir a rebufo`

  return (
    <div className={`rounded-inner p-4 ${selected ? 'bg-band' : 'bg-paper2'}`}>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onSelect(a.id)}
          className="flex min-h-9 items-baseline gap-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2"
          aria-label={`Elegir al atleta ${a.id}`}
        >
          <span className={`text-xl leading-none font-semibold tracking-[-0.01em] ${selected ? 'text-hero' : ''}`}>
            #{a.id}
          </span>
          <span className="label text-muted">sobre</span>
          <span className="text-xl leading-none font-semibold tracking-[-0.01em]">#{a.rival}</span>
        </button>
        <span className={`label ml-auto rounded-ui px-3 py-1.5 whitespace-nowrap ${ACTION[a.action].tone}`}>
          {ACTION[a.action].chip}
        </span>
      </div>

      <div className="mt-3 flex items-end gap-x-4 gap-y-1 max-sm:flex-wrap">
        <p className="lead-number shrink-0">{fmtPct(a.p_attack)}</p>
        <p className="min-w-0 flex-1 pb-1 text-sm leading-snug text-pretty text-muted">{detail}</p>
      </div>

      <AttackMap a={a} selected={selected} />

      <dl className="mt-3 grid grid-cols-3 gap-2">
        <Mini term="Energía">
          <span className="block">
            <span className="label font-normal text-muted">#{a.id}</span> {fmtPct(a.reserve)}
          </span>
          <span className="block">
            <span className="label font-normal text-muted">#{a.rival}</span> {fmtPct(a.rival_reserve)}
          </span>
        </Mini>
        <Mini term={`#${a.id} a rebufo`}>{fmtNum(a.draft_m, 0)} m</Mini>
        <Mini term="Pasar por fuera">{a.extra_m > 0 ? `+${fmtNum(a.extra_m, 1)} m` : 'sin costo'}</Mini>
      </dl>
    </div>
  )
}

function Mini({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-inner bg-surface px-3 py-2">
      <dt className="label text-muted">{term}</dt>
      <dd className="mt-0.5 text-sm font-semibold whitespace-nowrap tabular-nums">{children}</dd>
    </div>
  )
}

/**
 * Lo que le falta al rival hasta la meta, de "ahora" (izquierda) a la meta (derecha): curvas y
 * rectas de fondo, la probabilidad de pasarlo según dónde ataque (área) y la franja donde conviene.
 */
function AttackMap({ a, selected }: { a: Attack; selected: boolean }) {
  const [from, to] = a.window
  const span = Math.min(a.remaining, Math.max(450, from + 60))
  const x = (remaining: number) => ((span - remaining) / span) * 100
  const ink = selected ? 'var(--color-pick)' : 'var(--color-fg)'
  const segments = remainingSegments(span)
  const points = a.curve.filter(([m]) => m <= span).map(([m, p]) => `${x(m)},${100 - p * 100}`)
  const area = points.length > 1 ? `${points[0].split(',')[0]},100 ${points.join(' ')} ${points[points.length - 1].split(',')[0]},100` : ''

  return (
    <div className="mt-4" role="img" aria-label={`Probabilidad de pasar según dónde ataque; mejor punto a ${fmtNum(a.at_m, 0)} metros de la meta`}>
      <div className="relative">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="block h-12 w-full" aria-hidden="true">
          {area && <polygon points={area} fill={ink} opacity="0.14" />}
          {points.length > 1 && (
            <polyline
              points={points.join(' ')}
              fill="none"
              stroke={ink}
              strokeWidth="2"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        {/* franja donde conviene atacar y el punto ideal */}
        <span
          className="absolute inset-y-0 rounded-sm"
          style={{
            left: `${x(from)}%`,
            width: `${Math.max(1, x(to) - x(from))}%`,
            background: ink,
            opacity: 0.12,
          }}
          aria-hidden="true"
        />
        <span
          className="absolute inset-y-0 w-0.5 -translate-x-1/2 rounded-full"
          style={{ left: `${Math.min(99.5, x(a.at_m))}%`, background: ink }}
          aria-hidden="true"
        />
      </div>

      <div className="relative mt-1 h-3 overflow-hidden rounded-full">
        {segments.map(([f, e, curve]) => (
          <span
            key={`${f}-${e}`}
            className={`absolute inset-y-0 ${curve ? 'bg-lane-2' : 'bg-lane-1'}`}
            style={{ left: `${x(f)}%`, width: `${x(e) - x(f)}%` }}
          />
        ))}
      </div>

      <div className="label mt-1.5 flex justify-between text-muted">
        <span>faltan {fmtNum(span, 0)} m</span>
        <span>meta</span>
      </div>
    </div>
  )
}
