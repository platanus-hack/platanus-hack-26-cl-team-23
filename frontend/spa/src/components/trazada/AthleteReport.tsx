import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { fmtClock, fmtNum, fmtPct } from '../../trazada/format'
import {
  buildReport,
  defaultRival,
  inCurve,
  reportCsv,
  sAtX,
  type CurveCost,
  type Moment,
  type ProfilePoint,
  type Report,
  type Split,
} from '../../trazada/report'
import { useTactics } from '../../trazada/tactics'
import type { Race } from '../../trazada/types'
import { Button, Figure, Pending } from './ui'

type Props = {
  race: Race
  selectedId: number | undefined
  onSelect: (id: number) => void
  /** Lleva el video a ese segundo (y lo muestra). */
  onSeek: (t: number) => void
}

/**
 * Informe del atleta: toda la carrera de UN atleta, para su entrenador. Mide lo que hizo
 * (/api/athletes/) y, aparte y rotulado como pronóstico, lo que estima el modelo (/api/tactics/).
 * Cada tramo, curva y momento lleva el video a ese instante.
 */
export function AthleteReport({ race, selectedId, onSelect, onSeek }: Props) {
  const tactics = useTactics(race)
  const id = selectedId ?? race.defaultId ?? race.runners[0]?.id
  const [rivalChoice, setRivalChoice] = useState<number | undefined>(undefined)
  const rival = rivalChoice !== undefined && rivalChoice !== id ? rivalChoice : id === undefined ? undefined : defaultRival(race, id)
  const result = tactics.kind === 'ready' ? tactics.result : undefined
  const report = useMemo(() => (id === undefined ? undefined : buildReport(race, id, rival, result)), [race, id, rival, result])
  const t0 = race.raw.athletes?.t0 ?? 0

  if (!report || id === undefined) return <Pending>Elige un atleta en la lista para ver su informe.</Pending>
  if (report.series.length < 2)
    return (
      <div className="flex flex-col gap-[var(--section-gap)]">
        <Pickers race={race} id={id} rival={rival} onSelect={onSelect} onRival={setRivalChoice} />
        <Pending>A #{id} casi no se le midió en este video: no alcanza para un informe. Prueba con otro atleta.</Pending>
      </div>
    )

  return (
    <div className="flex flex-col gap-[var(--section-gap)]">
      <Pickers race={race} id={id} rival={rival} onSelect={onSelect} onRival={setRivalChoice} />
      <Summary race={race} r={report} />
      <Figure title="Dónde se ganó y perdió tiempo" meta={report.rival !== undefined ? `contra #${report.rival} · cada ${report.splits.step} m` : undefined}>
        <SplitsChart r={report} onSeek={onSeek} />
      </Figure>
      <Figure title="Perfil de velocidad" meta="m/s según los metros corridos">
        <ProfileChart r={report} />
      </Figure>
      <div className="grid items-start gap-[var(--section-gap)] lg:grid-cols-2">
        <Figure title="Por dónde corrió" meta="calle y metros de más">
          <Lanes r={report} onSeek={onSeek} />
        </Figure>
        <Figure title="Energía y rebufo" meta="rebufo medido · energía: pronóstico">
          <Energy r={report} state={tactics.kind} t0={t0} />
        </Figure>
      </div>
      <Figure title="Momentos clave" meta="cada uno lleva al video">
        <Moments r={report} t0={t0} onSeek={onSeek} />
      </Figure>
      <Figure title="Qué entrenar" meta="sale de los datos de arriba">
        <AdviceList r={report} />
      </Figure>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Atleta y rival
// ---------------------------------------------------------------------------------------------

function Pickers({
  race,
  id,
  rival,
  onSelect,
  onRival,
}: {
  race: Race
  id: number
  rival: number | undefined
  onSelect: (id: number) => void
  onRival: (id: number) => void
}) {
  // con atletas, cada corredor de la lista es un atleta medido
  const options = race.runners
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <Picker label="Atleta" value={id} onChange={onSelect} options={options.map((r) => r.id)} dot="bg-pick" />
      <Picker label="contra" value={rival} onChange={onRival} options={options.map((r) => r.id).filter((x) => x !== id)} dot="bg-other" />
    </div>
  )
}

function Picker({
  label,
  value,
  onChange,
  options,
  dot,
}: {
  label: string
  value: number | undefined
  onChange: (id: number) => void
  options: number[]
  dot: string
}) {
  const fieldId = `informe-${label}`
  return (
    <label htmlFor={fieldId} className="flex items-center gap-3 text-sm text-muted">
      {label}
      <span className="relative flex min-h-11 items-center gap-2 rounded-ui bg-surface pr-3 pl-4">
        <span className={`h-3 w-3 shrink-0 rounded-full ${dot}`} aria-hidden="true" />
        <select
          id={fieldId}
          value={value ?? ''}
          onChange={(e) => onChange(Number(e.target.value))}
          className="min-h-11 cursor-pointer appearance-none bg-transparent pr-5 text-base font-semibold text-fg focus-visible:outline-none"
        >
          {options.map((o) => (
            <option key={o} value={o}>
              #{o}
            </option>
          ))}
        </select>
        <span className="pointer-events-none absolute right-3 text-muted" aria-hidden="true">
          ▾
        </span>
      </span>
    </label>
  )
}

// ---------------------------------------------------------------------------------------------
// Resumen: una frase para cualquiera + cuatro cifras + cómo se midió
// ---------------------------------------------------------------------------------------------

function Summary({ race, r }: { race: Race; r: Report }) {
  const name = `#${r.id}`
  const place = r.rank ? `${r.rank.end}.º` : undefined
  const headline = place
    ? r.finished
      ? `${name} llegó ${place}.`
      : `${name} iba ${place} a falta de ${fmtNum(r.toGo, 0)} m.`
    : `${name} en esta carrera.`
  const compared = r.splits.items.length * r.splits.step
  const parts: ReactNode[] = []
  if (r.rival !== undefined && r.splits.items.length) {
    const lost = r.lost > 0.05
    const won = r.lost < -0.05
    parts.push(
      lost ? (
        <>
          Contra #{r.rival} perdió <b className="font-semibold text-fg">{fmtNum(r.lost, 2)} s</b> en los {compared} m comparados
          {r.curveShare >= 0.5 && <>, el {fmtPct(r.curveShare)} en las curvas</>}.
        </>
      ) : won ? (
        <>
          Contra #{r.rival} ganó <b className="font-semibold text-fg">{fmtNum(-r.lost, 2)} s</b> en los {compared} m comparados.
        </>
      ) : (
        <>Contra #{r.rival} corrió igual en los {compared} m comparados.</>
      ),
    )
  }
  if (r.extraM >= 0.5)
    parts.push(
      <>
        Corrió <b className="font-semibold text-fg">{fmtNum(r.extraM, 1)} m de más</b> por ir por fuera en las curvas (≈ {fmtNum(r.extraS, 2)} s).
      </>,
    )
  if (r.kick !== undefined && r.rivalKick !== undefined && Math.abs(r.rivalKick - r.kick) >= 20)
    parts.push(
      <>
        Lanzó el sprint <b className="font-semibold text-fg">{fmtNum(Math.abs(r.rivalKick - r.kick), 0)} m {r.kick < r.rivalKick ? 'después' : 'antes'}</b> que #{r.rival}.
      </>,
    )

  const gained = r.rank ? r.rank.start - r.rank.end : 0
  const pipeline = race.pipeline ? `${race.pipeline.detector} + ${race.pipeline.tracker}` : undefined

  return (
    <Figure title="Resumen" meta="toda la carrera">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <p className="text-3xl leading-tight font-semibold tracking-[-0.02em] text-balance">{headline}</p>
          {parts.length > 0 && (
            <p className="mt-3 text-lg leading-relaxed text-muted">
              {parts.map((p, i) => (
                <span key={i}>
                  {i > 0 && ' '}
                  {p}
                </span>
              ))}
            </p>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-2">
          <Tile
            term="Puestos"
            value={gained === 0 ? '=' : `${gained > 0 ? '▲' : '▼'} ${Math.abs(gained)}`}
            tone={gained > 0 ? 'text-gain' : gained < 0 ? 'text-loss' : ''}
            note={r.rank ? `de ${r.rank.start}.º a ${r.rank.end}.º` : undefined}
          />
          <Tile
            term={r.rival !== undefined ? `Contra #${r.rival}` : 'Contra el rival'}
            value={r.splits.items.length ? `${r.lost > 0 ? '+' : r.lost < 0 ? '−' : ''}${fmtNum(Math.abs(r.lost), 2)} s` : '—'}
            tone={r.lost > 0.05 ? 'text-loss' : r.lost < -0.05 ? 'text-gain' : ''}
            note={r.splits.items.length ? (r.lost > 0 ? 'más lento' : 'más rápido') : 'sin tramos comparables'}
          />
          <Tile term="Metros de más" value={`+${fmtNum(r.extraM, 1)} m`} tone={r.extraM >= 1 ? 'text-loss' : ''} note={`≈ ${fmtNum(r.extraS, 2)} s en curvas`} />
          <Tile term="A rebufo" value={fmtPct(r.draft)} note="del tiempo medido" />
        </dl>
      </div>
      <p className="label mt-6 flex flex-wrap gap-x-4 gap-y-1 text-muted">
        <span className="text-fg">Solo con el video de la transmisión</span>
        {pipeline && <span>{pipeline}</span>}
        <span>posición ± {fmtNum(r.sigma, 1)} m</span>
        <span>
          medido en {fmtNum(r.measuredM, 0)} de {fmtNum(r.distance, 0)} m
        </span>
      </p>
    </Figure>
  )
}

function Tile({ term, value, note, tone = '' }: { term: string; value: string; note?: string; tone?: string }) {
  return (
    <div className="bento flex min-h-24 flex-col justify-between gap-1 p-3">
      <dt className="label text-muted">{term}</dt>
      <dd>
        <span className={`stat-number block whitespace-nowrap ${tone}`}>{value}</span>
        {note && <span className="text-sm text-muted">{note}</span>}
      </dd>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Parciales contra el rival
// ---------------------------------------------------------------------------------------------

const HATCH = 'repeating-linear-gradient(45deg, transparent 0 4px, color-mix(in srgb, currentColor 35%, transparent) 4px 6px)'

function SplitsChart({ r, onSeek }: { r: Report; onSeek: (t: number) => void }) {
  const items = r.splits.items
  if (!items.length)
    return <Pending>No hay tramos en que se haya medido a los dos atletas: prueba contra otro rival.</Pending>
  const max = Math.max(0.1, ...items.map((s) => Math.abs(s.delta)))

  return (
    <div>
      <div className="relative flex h-48 gap-1" role="list" aria-label="Diferencia de tiempo por tramo">
        <span className="absolute inset-x-0 top-1/2 border-t border-line" aria-hidden="true" />
        {items.map((s) => (
          <SplitBar key={s.from} s={s} max={max} onSeek={onSeek} />
        ))}
      </div>
      <div className="label mt-2 flex gap-1 text-muted" aria-hidden="true">
        {items.map((s) => (
          <span key={s.from} className="min-w-0 flex-1 truncate text-center">
            {s.to}
          </span>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
        <Key className="bg-loss">perdió tiempo</Key>
        <Key className="bg-gain">ganó tiempo</Key>
        <Key className="text-other" style={{ background: HATCH }}>
          estimado: la cámara no lo mostraba
        </Key>
        <Key className="bg-band">curva</Key>
      </div>
    </div>
  )
}

function SplitBar({ s, max, onSeek }: { s: Split; max: number; onSeek: (t: number) => void }) {
  const h = (Math.abs(s.delta) / max) * 42 // % del alto: nunca toca el borde
  const lost = s.delta > 0
  const tone = lost ? 'text-loss' : 'text-gain'
  const label = `${lost ? '+' : '−'}${fmtNum(Math.abs(s.delta), 2)}`
  return (
    <button
      type="button"
      role="listitem"
      onClick={() => onSeek(s.t)}
      aria-label={`Tramo ${s.from} a ${s.to} m: ${lost ? 'perdió' : 'ganó'} ${fmtNum(Math.abs(s.delta), 2)} segundos${s.estimated ? ', estimado' : ''}. Ver en el video.`}
      className={`group relative min-w-0 flex-1 rounded-sm transition-colors hover:bg-paper2 focus-visible:outline-2 focus-visible:outline-offset-2 ${s.curve >= 0.5 ? 'bg-band/60' : ''}`}
    >
      <span
        className={`absolute inset-x-[18%] rounded-[3px] ${tone} ${s.estimated ? 'ring-2 ring-current ring-inset' : lost ? 'bg-loss' : 'bg-gain'}`}
        style={{
          height: `${Math.max(h, 1)}%`,
          ...(lost ? { bottom: '50%' } : { top: '50%' }),
          ...(s.estimated ? { background: HATCH } : {}),
        }}
      />
      <span
        className={`label absolute inset-x-0 text-center whitespace-nowrap ${tone} max-md:hidden`}
        style={lost ? { bottom: `calc(50% + ${h}% + 4px)` } : { top: `calc(50% + ${h}% + 4px)` }}
      >
        {label}
      </span>
    </button>
  )
}

function Key({ className = '', style, children }: { className?: string; style?: CSSProperties; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-3.5 w-3.5 rounded-[4px] ${className}`} style={style} aria-hidden="true" />
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------------------------
// Perfil de velocidad
// ---------------------------------------------------------------------------------------------

function ProfileChart({ r }: { r: Report }) {
  const all = [...r.profile, ...r.rivalProfile]
  if (r.profile.length < 3) return <Pending>Hay muy pocas mediciones para dibujar su velocidad.</Pending>
  const x0 = Math.min(...all.map((p) => p.x))
  const x1 = Math.max(...all.map((p) => p.x))
  const v0 = Math.floor((Math.min(...all.map((p) => p.v)) - 0.1) * 2) / 2
  const v1 = Math.ceil((Math.max(...all.map((p) => p.v)) + 0.1) * 2) / 2
  const X = (x: number) => ((x - x0) / Math.max(1, x1 - x0)) * 100
  const Y = (v: number) => 100 - ((v - v0) / Math.max(0.1, v1 - v0)) * 100
  const line = (pts: ProfilePoint[]) => {
    // corta la línea donde no se midió (más de 30 m sin datos)
    const segs: string[][] = []
    pts.forEach((p, i) => {
      if (i === 0 || p.x - pts[i - 1].x > 30) segs.push([])
      segs[segs.length - 1].push(`${X(p.x)},${Y(p.v)}`)
    })
    return segs.filter((s) => s.length > 1)
  }
  const curves = curveSpans(x0, x1, r.distance)
  const kicks = [
    r.rivalKick !== undefined && { at: r.distance - r.rivalKick, text: `#${r.rival} lanza a ${fmtNum(r.rivalKick, 0)} m`, me: false },
    r.kick !== undefined && { at: r.distance - r.kick, text: `#${r.id} lanza a ${fmtNum(r.kick, 0)} m`, me: true },
  ].filter((k): k is { at: number; text: string; me: boolean } => !!k)

  return (
    <div>
      <div className="relative h-56 rounded-inner bg-paper2">
        {curves.map(([a, b]) => (
          <span key={a} className="absolute inset-y-0 bg-band/70" style={{ left: `${X(a)}%`, width: `${X(b) - X(a)}%` }} aria-hidden="true" />
        ))}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" role="img" aria-label={`Velocidad de #${r.id} y de #${r.rival ?? ''} a lo largo de la carrera`}>
          {line(r.rivalProfile).map((s, i) => (
            <polyline key={`r${i}`} points={s.join(' ')} fill="none" stroke="var(--color-other)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          ))}
          {line(r.profile).map((s, i) => (
            <polyline key={`m${i}`} points={s.join(' ')} fill="none" stroke="var(--color-pick)" strokeWidth={3} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          ))}
        </svg>
        {kicks.map((k) => (
          <span
            key={k.text}
            className={`absolute inset-y-0 border-l-2 border-dashed ${k.me ? 'border-pick' : 'border-other'}`}
            style={{ left: `${X(k.at)}%` }}
            aria-hidden="true"
          >
            <span className={`label absolute -translate-x-full pr-2 whitespace-nowrap ${k.me ? 'bottom-2 text-hero' : 'top-2 text-muted'}`}>{k.text}</span>
          </span>
        ))}
        <span className="label absolute top-2 left-2 text-muted">{fmtNum(v1, 1)} m/s</span>
        <span className="label absolute bottom-2 left-2 text-muted">{fmtNum(v0, 1)}</span>
      </div>
      <div className="label mt-1.5 flex justify-between text-muted">
        <span>{fmtNum(x0, 0)} m</span>
        <span>{fmtNum(x1, 0)} m</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
        <Key className="h-1 bg-pick">#{r.id}</Key>
        {r.rival !== undefined && <Key className="h-0.5 bg-other">#{r.rival}</Key>}
        <Key className="bg-band">curva</Key>
        <span className="ml-auto">
          máxima: #{r.id} {fmtNum(Math.max(...r.profile.map((p) => p.v)), 1)} m/s
          {r.rivalProfile.length > 0 && ` · #${r.rival} ${fmtNum(Math.max(...r.rivalProfile.map((p) => p.v)), 1)} m/s`}
        </span>
      </div>
    </div>
  )
}

/** Tramos de curva (en metros desde la salida) entre x0 y x1. */
function curveSpans(x0: number, x1: number, distance: number): [number, number][] {
  const out: [number, number][] = []
  let from: number | undefined
  for (let x = x0; x <= x1; x += 2) {
    const c = inCurve(sAtX(x, distance))
    if (c && from === undefined) from = x
    if (!c && from !== undefined) {
      out.push([from, x])
      from = undefined
    }
  }
  if (from !== undefined) out.push([from, x1])
  return out
}

// ---------------------------------------------------------------------------------------------
// Calle y metros de más
// ---------------------------------------------------------------------------------------------

const LANE_TONE = ['bg-line', 'bg-other/60', 'bg-other', 'bg-fg/70']

function Lanes({ r, onSeek }: { r: Report; onSeek: (t: number) => void }) {
  const D = r.distance
  const worst = Math.max(0.1, ...r.curves.map((c) => c.extra))
  return (
    <div>
      <p className="text-lg leading-relaxed text-muted">
        {r.extraM >= 0.5 ? (
          <>
            <b className="font-semibold text-fg">{fmtNum(r.extraM, 1)} m de más</b> que pegado al bordillo. A su ritmo, eso son {fmtNum(r.extraS, 2)} s.
          </>
        ) : (
          'Corrió las curvas pegado al bordillo: casi sin metros de más.'
        )}
      </p>
      <p className="label mt-5 text-muted">Calle a lo largo de la carrera</p>
      <div className="relative mt-2 h-7 overflow-hidden rounded-inner bg-paper2" role="img" aria-label="Calle por la que corrió en cada tramo medido">
        {r.lanes.map((b) => (
          <span
            key={b.from}
            className={`absolute inset-y-0 grid place-items-center text-xs font-semibold text-bg ${LANE_TONE[Math.min(b.lane, 4) - 1]}`}
            style={{ left: `${(b.from / D) * 100}%`, width: `${((b.to - b.from) / D) * 100}%` }}
          >
            {(b.to - b.from) / D > 0.05 ? b.lane : ''}
          </span>
        ))}
      </div>
      <div className="label mt-1.5 flex justify-between text-muted">
        <span>salida</span>
        <span>sin color: no se le vio</span>
        <span>meta</span>
      </div>
      {r.curves.length > 0 && (
        <ul className="mt-5 flex flex-col">
          {r.curves.map((c) => (
            <CurveRow key={c.x} c={c} worst={worst} onSeek={onSeek} />
          ))}
        </ul>
      )}
    </div>
  )
}

function CurveRow({ c, worst, onSeek }: { c: CurveCost; worst: number; onSeek: (t: number) => void }) {
  return (
    <li className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)_4rem_4rem_auto] items-center gap-3 border-t border-line py-2 text-sm">
      <span className="text-muted">Curva a los {fmtNum(c.x, 0)} m</span>
      <span className="h-2 overflow-hidden rounded-full bg-paper2">
        <span className="block h-2 rounded-full bg-loss" style={{ width: `${(c.extra / worst) * 100}%` }} />
      </span>
      <span className="text-right tabular-nums">+{fmtNum(c.extra, 1)} m</span>
      <span className="text-right text-muted tabular-nums">{fmtNum(c.seconds, 2)} s</span>
      <SeeButton onClick={() => onSeek(c.t)} label={`Ver la curva de los ${fmtNum(c.x, 0)} metros`} />
    </li>
  )
}

// ---------------------------------------------------------------------------------------------
// Energía (pronóstico) y rebufo (medido)
// ---------------------------------------------------------------------------------------------

function Energy({ r, state, t0 }: { r: Report; state: ReturnType<typeof useTactics>['kind']; t0: number }) {
  const pts = r.reserve
  const last = pts[pts.length - 1]
  return (
    <div>
      <dl className="grid grid-cols-2 gap-2">
        <Tile term="A rebufo" value={fmtPct(r.draft)} note="medido: 0,3–2 m detrás de otro" />
        <Tile term="Reserva" value={last ? fmtPct(last.reserve) : '—'} note={last ? `pronóstico · al ${fmtClock(last.t - t0)}` : 'pronóstico'} />
      </dl>
      <div className="mt-5">
        {state === 'loading' ? (
          <Pending>Calculando la energía con el modelo…</Pending>
        ) : state !== 'ready' ? (
          <Pending>El pronóstico de energía no está disponible para este video.</Pending>
        ) : pts.length < 2 ? (
          <Pending>El modelo estima la energía solo cuando el atleta va en un duelo a menos de 15 m de otro, y aquí casi no pasó.</Pending>
        ) : (
          <ReserveChart pts={pts} t0={t0} />
        )}
      </div>
    </div>
  )
}

function ReserveChart({ pts, t0 }: { pts: Report['reserve']; t0: number }) {
  const a = pts[0].t
  const b = pts[pts.length - 1].t
  const X = (t: number) => ((t - a) / Math.max(1, b - a)) * 100
  const segs: string[][] = []
  pts.forEach((p, i) => {
    if (i === 0 || p.t - pts[i - 1].t > 3) segs.push([])
    segs[segs.length - 1].push(`${X(p.t)},${100 - p.reserve * 100}`)
  })
  return (
    <div>
      <div className="relative h-36 rounded-inner bg-paper2">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" role="img" aria-label="Reserva de energía estimada en el tiempo">
          {segs.map((s, i) =>
            s.length > 1 ? (
              <polyline key={i} points={s.join(' ')} fill="none" stroke="var(--color-pick)" strokeWidth={3} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            ) : null,
          )}
        </svg>
        <span className="label absolute top-1.5 left-2 text-muted">100 %</span>
        <span className="label absolute bottom-1.5 left-2 text-muted">0 %</span>
      </div>
      <div className="label mt-1.5 flex justify-between text-muted">
        <span>{fmtClock(a - t0)}</span>
        <span>pronóstico · solo en duelos</span>
        <span>{fmtClock(b - t0)}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Momentos clave
// ---------------------------------------------------------------------------------------------

function momentText(m: Moment): { title: string; detail: string; dot: string } {
  if (m.kind === 'passed') return { title: `Adelanta a #${m.other}`, detail: m.curve ? 'en la curva: le cuesta metros de más' : 'en la recta', dot: 'bg-gain' }
  if (m.kind === 'lost') return { title: `Lo pasa #${m.other}`, detail: m.curve ? 'en la curva' : 'en la recta', dot: 'bg-loss' }
  return { title: `Ventana para atacar a #${m.other}`, detail: `pronóstico · ${fmtPct(m.p)} de que salga bien`, dot: 'bg-pick' }
}

function Moments({ r, t0, onSeek }: { r: Report; t0: number; onSeek: (t: number) => void }) {
  if (!r.moments.length) return <Pending>En lo que se midió no hubo adelantamientos ni ventanas de ataque para #{r.id}.</Pending>
  return (
    <ul className="flex flex-col">
      {r.moments.map((m) => {
        const txt = momentText(m)
        return (
          <li key={`${m.kind}-${m.t}-${m.other}`} className="grid grid-cols-[4.5rem_0.75rem_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-3 first:border-t-0">
            <span className="label text-muted tabular-nums">{fmtClock(m.t - t0)}</span>
            <span className={`h-3 w-3 rounded-full ${txt.dot}`} aria-hidden="true" />
            <span className="min-w-0">
              <span className="block font-semibold">{txt.title}</span>
              <span className="block text-sm text-muted">{txt.detail}</span>
            </span>
            <SeeButton onClick={() => onSeek(m.t)} label={`Ver: ${txt.title}`} />
          </li>
        )
      })}
    </ul>
  )
}

function SeeButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="inline-flex min-h-11 items-center gap-2 rounded-ui bg-paper2 px-4 text-sm font-semibold transition-colors hover:bg-line focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <svg width="10" height="10" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M3 1.5v11l9-5.5z" fill="currentColor" />
      </svg>
      Ver
    </button>
  )
}

// ---------------------------------------------------------------------------------------------
// Qué entrenar
// ---------------------------------------------------------------------------------------------

function AdviceList({ r }: { r: Report }) {
  const download = () => {
    const blob = new Blob([reportCsv(r)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trazada-atleta-${r.id}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <div>
      {r.advice.length === 0 ? (
        <Pending>Con lo que se midió no aparece nada claro que corregir.</Pending>
      ) : (
        <ul className="grid gap-2 md:grid-cols-3">
          {r.advice.map((a) => (
            <li key={a.title} className="bento flex flex-col gap-2 p-4">
              <span className="label text-muted">{a.forecast ? 'pronóstico' : a.good ? 'hoy' : 'vale'}</span>
              <span className={`stat-number ${a.good ? 'text-gain' : ''}`}>{a.value}</span>
              <span className="font-semibold">{a.title}</span>
              <span className="text-sm leading-relaxed text-muted">{a.detail}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-5">
        <Button onClick={download}>Exportar datos (CSV)</Button>
        <span className="text-sm text-muted">Las mediciones de #{r.id} cuadro a cuadro, para seguir su progreso entre carreras.</span>
      </div>
    </div>
  )
}
