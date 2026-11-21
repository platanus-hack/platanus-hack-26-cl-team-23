import { useEffect, useRef, useState } from 'react'
import { curveRanges, type SeriesPoint } from '../../trazada/analysis'
import { LANE, LAP } from '../../trazada/geometry'
import { fmtMeters, fmtNum } from '../../trazada/format'
import type { RunnerInfo } from '../../trazada/types'

type Props = {
  series: Map<number, SeriesPoint[]>
  runners: RunnerInfo[]
  selectedId: number
  currentS: number | undefined // dónde va el elegido ahora (para la línea de tiempo)
}

const M = { top: 22, right: 64, bottom: 26, left: 44 }
const ROW_H = 120
const GAP = 34

/**
 * Telemetría del corredor: dos gráficos que comparten el eje X (metros para la meta).
 * Arriba: qué tan lejos de la cuerda corrió. Abajo: metros extra acumulados.
 * Así se ve el porqué (se abrió en la curva) y la consecuencia (sumó metros).
 */
export function RunnerTelemetry({ series, runners, selectedId, currentS }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  const [hoverS, setHoverS] = useState<number | null>(null)

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const all = [...series.values()].flat()
  if (all.length === 0) return null
  const sMin = Math.min(...all.map((p) => p.s))
  const sMax = Math.max(...all.map((p) => p.s))
  const dMax = Math.max(2, Math.ceil((Math.max(...all.map((p) => p.d)) + 0.3) * 2) / 2)
  const eMax = Math.max(1, Math.ceil(Math.max(...all.map((p) => p.extra)) + 0.5))
  const H = M.top + ROW_H * 2 + GAP + M.bottom
  const plotW = Math.max(10, w - M.left - M.right)

  const x = (s: number) => M.left + ((s - sMin) / (sMax - sMin)) * plotW
  const yD = (d: number) => M.top + ROW_H - (d / dMax) * ROW_H
  const top2 = M.top + ROW_H + GAP
  const yE = (e: number) => top2 + ROW_H - (e / eMax) * ROW_H
  const path = (pts: SeriesPoint[], y: (p: SeriesPoint) => number) =>
    pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.s).toFixed(1)},${y(p).toFixed(1)}`).join('')

  const label = (id: number) => runners.find((r) => r.id === id)?.label ?? `#${id}`
  const ids = [...series.keys()].sort((a, b) => Number(a === selectedId) - Number(b === selectedId))
  const sel = series.get(selectedId) ?? []
  const selLast = sel[sel.length - 1]
  const toFinish = (s: number) => LAP - s
  const ticks = niceTicks(toFinish(sMax), toFinish(sMin), 5)

  // Lectura en el punto bajo el cursor: el valor de cada corredor en esa posición
  const readAt = (pts: SeriesPoint[], s: number) => {
    let best = pts[0]
    for (const p of pts) if (Math.abs(p.s - s) < Math.abs(best.s - s)) best = p
    return best
  }
  const readout =
    hoverS !== null
      ? ids
          .map((id) => ({ id, p: readAt(series.get(id)!, hoverS) }))
          .filter((r) => Math.abs(r.p.s - hoverS) < 3)
          .sort((a, b) => b.p.extra - a.p.extra)
      : []

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - rect.left
    if (px < M.left || px > M.left + plotW) return setHoverS(null)
    setHoverS(sMin + ((px - M.left) / plotW) * (sMax - sMin))
  }

  return (
    <div ref={wrap} className="relative w-full">
      {w > 0 && (
        <svg
          width={w}
          height={H}
          onPointerMove={onMove}
          onPointerLeave={() => setHoverS(null)}
          role="img"
          aria-label={`Distancia a la cuerda y metros extra de ${label(selectedId)} a lo largo de la carrera`}
          className="block touch-pan-y"
        >
          {/* tramos de curva sombreados en ambos gráficos */}
          {curveRanges(sMin, sMax).map(([a, b]) => (
            <g key={a}>
              <rect x={x(a)} y={M.top} width={x(b) - x(a)} height={ROW_H} fill="var(--color-accent)" fillOpacity={0.06} />
              <rect x={x(a)} y={top2} width={x(b) - x(a)} height={ROW_H} fill="var(--color-accent)" fillOpacity={0.06} />
              <text x={(x(a) + x(b)) / 2} y={M.top - 8} textAnchor="middle" className="fill-accent text-[10px] font-semibold">
                curva
              </text>
            </g>
          ))}

          {/* --- Gráfico 1: distancia a la cuerda --- */}
          <ChartTitle x={M.left} y={M.top + 12} text="Distancia a la cuerda" />
          {[0, 1, 2, 3].filter((v) => v <= dMax).map((v) => (
            <g key={v}>
              <line x1={M.left} x2={M.left + plotW} y1={yD(v)} y2={yD(v)} stroke="var(--color-line)" />
              <text x={M.left - 8} y={yD(v) + 3} textAnchor="end" className="fill-muted font-mono text-[10px]">
                {v} m
              </text>
            </g>
          ))}
          {/* límite entre pista 1 y pista 2 */}
          <line x1={M.left} x2={M.left + plotW} y1={yD(LANE)} y2={yD(LANE)} stroke="rgba(243,233,226,.35)" strokeDasharray="2 3" />
          <text x={M.left + plotW + 6} y={yD(LANE) + 3} className="fill-muted text-[10px]">
            pista 2
          </text>
          {ids.map((id) => (
            <path
              key={id}
              d={path(series.get(id)!, (p) => yD(p.d))}
              fill="none"
              stroke={id === selectedId ? 'var(--color-pick)' : 'rgba(170,180,195,.35)'}
              strokeWidth={id === selectedId ? 2 : 1}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}

          {/* --- Gráfico 2: metros extra acumulados --- */}
          <ChartTitle x={M.left} y={top2 + 12} text="Metros extra acumulados" />
          {niceTicks(0, eMax, 4).map((v) => (
            <g key={v}>
              <line x1={M.left} x2={M.left + plotW} y1={yE(v)} y2={yE(v)} stroke="var(--color-line)" />
              <text x={M.left - 8} y={yE(v) + 3} textAnchor="end" className="fill-muted font-mono text-[10px]">
                {v} m
              </text>
            </g>
          ))}
          {ids.map((id) => (
            <path
              key={id}
              d={path(series.get(id)!, (p) => yE(p.extra))}
              fill="none"
              stroke={id === selectedId ? 'var(--color-pick)' : 'rgba(170,180,195,.35)'}
              strokeWidth={id === selectedId ? 2 : 1}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {selLast && (
            <g>
              <circle cx={x(selLast.s)} cy={yE(selLast.extra)} r={4.5} fill="var(--color-pick)" stroke="var(--color-panel)" strokeWidth={2} />
              <text x={x(selLast.s) + 8} y={yE(selLast.extra) + 4} className="fill-fg font-mono text-[11px] font-bold">
                {fmtMeters(selLast.extra)}
              </text>
            </g>
          )}

          {/* eje X compartido */}
          {ticks.map((v) => (
            <text key={v} x={x(LAP - v)} y={H - 8} textAnchor="middle" className="fill-muted font-mono text-[10px]">
              {v}
            </text>
          ))}
          <text x={M.left + plotW + 6} y={H - 8} className="fill-muted text-[10px]">
            m a meta
          </text>

          {/* dónde va ahora el elegido */}
          {currentS !== undefined && currentS >= sMin && (
            <line x1={x(currentS)} x2={x(currentS)} y1={M.top} y2={top2 + ROW_H} stroke="rgba(233,238,244,.35)" />
          )}
          {/* cursor */}
          {hoverS !== null && (
            <line x1={x(hoverS)} x2={x(hoverS)} y1={M.top} y2={top2 + ROW_H} stroke="rgba(233,238,244,.7)" />
          )}
        </svg>
      )}

      {hoverS !== null && readout.length > 0 && (
        <div
          className="pointer-events-none absolute top-6 z-10 min-w-40 rounded-lg border border-line bg-bg/95 px-3 py-2 text-xs shadow-xl"
          style={x(hoverS) > w / 2 ? { right: w - x(hoverS) + 10 } : { left: x(hoverS) + 10 }}
        >
          <p className="mb-1 text-muted">{fmtNum(LAP - hoverS, 0)} m para la meta</p>
          {readout.map(({ id, p }) => (
            <p key={id} className={`flex items-center gap-2 font-mono tabular-nums ${id === selectedId ? 'text-fg' : 'text-muted'}`}>
              <span
                className="inline-block h-0.5 w-3"
                style={{ background: id === selectedId ? 'var(--color-pick)' : 'rgba(170,180,195,.6)' }}
              />
              <b className="w-12 font-bold">{fmtMeters(p.extra)}</b>
              <span>{fmtNum(p.d, 2)} m cuerda</span>
              <span className="ml-auto pl-2">{label(id)}</span>
            </p>
          ))}
        </div>
      )}

      <div className="mt-1 flex items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 bg-pick" /> {label(selectedId)}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-px w-4 bg-other/60" /> resto de los corredores
        </span>
      </div>
    </div>
  )
}

function ChartTitle({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <text x={x + 6} y={y} className="fill-fg text-[11px] font-semibold">
      {text}
    </text>
  )
}

function niceTicks(a: number, b: number, n: number) {
  const span = b - a
  const raw = span / n
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(a / step) * step; v <= b + 1e-9; v += step) out.push(+v.toFixed(6))
  return out
}
