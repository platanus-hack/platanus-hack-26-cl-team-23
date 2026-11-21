import { useEffect, useMemo, useRef, useState } from 'react'
import { curveRanges, overtakeBalance, type BalancePoint } from '../../trazada/analysis'
import { LAP } from '../../trazada/geometry'
import { fmtMeters, fmtNum } from '../../trazada/format'
import type { Race } from '../../trazada/types'

type Props = {
  race: Race
  selectedId: number
  t: number // tiempo actual del video: lo ya corrido se dibuja fuerte, lo que viene, tenue
}

const M = { top: 24, right: 56, bottom: 28, left: 44 }
const H = 240

/**
 * «Balance de adelantar»: ventaja del corredor sobre el grupo a lo largo de la carrera.
 * Línea verde = lo que ganó de verdad. Línea punteada = lo que habría ganado por la cuerda.
 * La franja naranja entre ambas = lo que le costó ir por fuera.
 */
export function BalanceChart({ race, selectedId, t }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const { points, changes } = useMemo(() => overtakeBalance(race, selectedId), [race, selectedId])
  const label = race.runners.find((r) => r.id === selectedId)?.label ?? `#${selectedId}`
  // Las cifras de la izquierda también son "a este instante", igual que el gráfico.
  const now = nowPoint(points, t)

  return (
    <div className="flex flex-col gap-6 md:flex-row md:gap-8">
      <div className="flex shrink-0 flex-col gap-3 md:w-64">
        <h2 className="font-display text-2xl leading-tight font-bold">Balance de adelantar · {label}</h2>
        <p className="text-sm leading-relaxed text-muted">
          Ventaja sobre el grupo, en metros. La franja naranja es lo que le costó ir por fuera.
        </p>
        {now && (
          <dl className="mt-1 flex flex-col gap-2 text-sm">
            <Row term="Le saca al grupo" value={fmtMeters(now.real)} strong />
            <Row term="Paga por ir por fuera" value={fmtMeters(now.real - now.ideal)} />
            <Row term="Por la cuerda (si pudiera)" value={fmtMeters(now.ideal)} />
          </dl>
        )}
      </div>
      <div ref={wrap} className="min-w-0 flex-1">
        {w > 0 && points.length > 1 && <Plot points={points} changes={changes} w={w} t={t} label={label} />}
      </div>
    </div>
  )
}

/** Último punto ya ocurrido al tiempo t (o el primero, si la carrera aún no llega). */
function nowPoint(points: BalancePoint[], t: number) {
  let out = points[0]
  for (const p of points) if (p.t <= t) out = p
  return out
}

function Row({ term, value, strong }: { term: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted">{term}</dt>
      <dd className={`font-mono font-bold whitespace-nowrap tabular-nums ${strong ? 'text-hero' : 'text-fg'}`}>{value}</dd>
    </div>
  )
}

function Plot({
  points,
  changes,
  w,
  t,
  label,
}: {
  points: BalancePoint[]
  changes: ReturnType<typeof overtakeBalance>['changes']
  w: number
  t: number
  label: string
}) {
  const sMin = points[0].s
  const sMax = points[points.length - 1].s
  const yLo = Math.min(0, ...points.map((p) => p.real)) - 0.5
  const yHi = Math.max(1, ...points.map((p) => p.ideal)) + 0.5
  const plotW = Math.max(10, w - M.left - M.right)
  const plotH = H - M.top - M.bottom
  const x = (s: number) => M.left + ((s - sMin) / (sMax - sMin || 1)) * plotW
  const y = (v: number) => M.top + plotH - ((v - yLo) / (yHi - yLo)) * plotH
  const line = (pts: BalancePoint[], k: 'real' | 'ideal') =>
    pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.s).toFixed(1)},${y(p[k]).toFixed(1)}`).join('')
  // Franja = ida por la línea ideal y vuelta por la real.
  const band = (pts: BalancePoint[]) =>
    pts.length < 2 ? '' : `${line(pts, 'ideal')}${line([...pts].reverse(), 'real').replace(/^M/, 'L')}Z`

  // Corte causal: lo corrido hasta ahora va sólido; lo que viene, apenas insinuado.
  const now = nowPoint(points, t)!
  const past = points.filter((p) => p.t <= now.t)
  const yTicks = ticks(yLo, yHi, 5)
  const xTicks = ticks(LAP - sMax, LAP - sMin)

  return (
    <svg
      width={w}
      height={H}
      role="img"
      aria-label={`Balance de adelantar de ${label}: ventaja real y ventaja si hubiera ido por la cuerda`}
      className="block"
    >
      {curveRanges(sMin, sMax).map(([a, b]) => (
        <g key={a}>
          <rect x={x(a)} y={M.top} width={x(b) - x(a)} height={plotH} fill="var(--color-accent)" fillOpacity={0.06} />
          <text x={(x(a) + x(b)) / 2} y={M.top - 8} textAnchor="middle" className="fill-accent text-[10px] font-semibold">
            curva
          </text>
        </g>
      ))}
      {yTicks.map((v) => (
        <g key={v}>
          <line x1={M.left} x2={M.left + plotW} y1={y(v)} y2={y(v)} stroke="var(--color-line)" strokeOpacity={v === 0 ? 0 : 1} />
          <text x={M.left - 8} y={y(v) + 3} textAnchor="end" className="fill-muted font-mono text-[10px]">
            {v > 0 ? `+${v}` : v}
          </text>
        </g>
      ))}
      <line x1={M.left} x2={M.left + plotW} y1={y(0)} y2={y(0)} stroke="var(--color-muted)" strokeOpacity={0.6} />

      {/* el futuro, tenue */}
      <g opacity={0.18}>
        <path d={band(points)} fill="var(--color-accent)" fillOpacity={0.5} />
        <path d={line(points, 'ideal')} fill="none" stroke="var(--color-fg)" strokeWidth={1.5} strokeDasharray="6 6" />
        <path d={line(points, 'real')} fill="none" stroke="var(--color-pick)" strokeWidth={2} />
      </g>
      {/* lo corrido, sólido */}
      <path d={band(past)} fill="var(--color-accent)" fillOpacity={0.16} />
      <path d={line(past, 'ideal')} fill="none" stroke="var(--color-fg)" strokeWidth={2} strokeDasharray="8 7" />
      <path d={line(past, 'real')} fill="none" stroke="var(--color-pick)" strokeWidth={3} strokeLinejoin="round" />

      {changes
        .filter((c) => c.s <= now.s)
        .map((c) => (
          <g key={c.s}>
            <circle cx={x(c.s)} cy={y(c.real)} r={5} fill="var(--color-pick)" stroke="var(--color-panel)" strokeWidth={2} />
            <text x={x(c.s)} y={y(c.real) + 20} textAnchor="middle" className="fill-fg text-[11px] font-semibold">
              {c.to < c.from ? '▲' : '▼'} {c.to}.º
            </text>
          </g>
        ))}

      {/* ahora */}
      <line x1={x(now.s)} x2={x(now.s)} y1={M.top} y2={M.top + plotH} stroke="var(--color-fg)" strokeOpacity={0.35} />
      <circle cx={x(now.s)} cy={y(now.real)} r={4} fill="var(--color-pick)" />
      <text x={x(now.s) + 8} y={y(now.real) + 4} className="fill-hero font-mono text-[11px] font-bold">
        {fmtNum(now.real, 1)}
      </text>
      <text x={x(now.s) + 8} y={y(now.ideal) + 4} className="fill-fg font-mono text-[11px] font-bold">
        {fmtNum(now.ideal, 1)}
      </text>

      {xTicks.map((v) => (
        <text key={v} x={x(LAP - v)} y={H - 8} textAnchor="middle" className="fill-muted font-mono text-[10px]">
          {v}
        </text>
      ))}
      <text x={M.left + plotW + 8} y={H - 8} className="fill-muted text-[10px]">
        m a meta
      </text>
    </svg>
  )
}

/** Marcas "redondas" (1, 2, 5, 10…) entre a y b. */
function ticks(a: number, b: number, n = 4) {
  const raw = (b - a) / n
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(a / step) * step; v <= b + 1e-9; v += step) out.push(+v.toFixed(6))
  return out
}
