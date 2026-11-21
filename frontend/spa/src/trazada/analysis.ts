// Cálculos derivados para la ficha del corredor. Solo leen el modelo interno `Race`.
import { isCurve } from './geometry'
import type { Race, RaceFrame } from './types'

export type SeriesPoint = { t: number; s: number; d: number; extra: number }

/** Serie temporal por corredor: dónde estaba (s, d) y cuántos metros extra llevaba. */
export function runnerSeries(race: Race): Map<number, SeriesPoint[]> {
  const out = new Map<number, SeriesPoint[]>()
  for (const f of race.frames)
    for (const r of f.runners) {
      if (r.s === undefined || r.d === undefined) continue
      if (!out.has(r.id)) out.set(r.id, [])
      out.get(r.id)!.push({ t: f.t, s: r.s, d: r.d, extra: r.extraM ?? 0 })
    }
  return out
}

/** Puesto de cada corredor en un cuadro (1 = adelante). */
export function ranksAt(frame: RaceFrame | undefined): Map<number, number> {
  const rows = (frame?.runners ?? []).filter((r) => r.s !== undefined).sort((a, b) => b.s! - a.s!)
  return new Map(rows.map((r, i) => [r.id, i + 1]))
}

export function averageSpeed(series: SeriesPoint[] | undefined) {
  if (!series || series.length < 2) return undefined
  const a = series[0]
  const b = series[series.length - 1]
  return (b.s - a.s) / (b.t - a.t)
}

/** Tramos de curva dentro de [s0, s1], para sombrearlos en los gráficos. */
export function curveRanges(s0: number, s1: number): [number, number][] {
  const out: [number, number][] = []
  let start: number | null = null
  for (let s = s0; s <= s1; s += 0.5) {
    if (isCurve(s) && start === null) start = s
    if (!isCurve(s) && start !== null) {
      out.push([start, s])
      start = null
    }
  }
  if (start !== null) out.push([start, s1])
  return out
}

/** Regla de la curva: ir `lateral` metros más afuera durante una curva completa de 180° suma π·lateral metros. */
export const extraPerCurve = (lateral: number) => Math.PI * lateral

/** Nombres de las 6 zonas de Daniel. */
export const ZONE_NAMES: Record<number, string> = {
  1: 'Curva 1 · salida',
  2: 'Recta opuesta',
  3: 'Curva 2 · entrada',
  4: 'Curva 2 · salida',
  5: 'Recta final',
  6: 'Curva 1 · entrada',
}

export type BalancePoint = {
  t: number
  s: number // dónde iba el corredor (m por la línea de medición)
  real: number // ventaja sobre el grupo, relativa al inicio (m)
  ideal: number // la misma ventaja si no hubiera corrido metros extra (m)
  rank: number // puesto en ese instante (1 = adelante)
}
export type RankChange = { s: number; real: number; from: number; to: number }

/**
 * «Balance de adelantar»: ¿le convino al corredor ir por fuera?
 * - real: cuánto le sacó al resto. Es su s menos el promedio de s de los demás en el mismo
 *   instante, y se resta el valor inicial para que la curva parta en 0.
 * - ideal: real + los metros extra que llevaba. Es lo que habría ganado por la cuerda.
 * La diferencia entre ambas es lo que le costó abrirse. Solo usa cuadros pasados en cada punto.
 */
export function overtakeBalance(race: Race, id: number): { points: BalancePoint[]; changes: RankChange[] } {
  const points: BalancePoint[] = []
  let base: { adv: number; extra: number } | undefined
  for (const f of race.frames) {
    const me = f.runners.find((r) => r.id === id)
    const others = f.runners.filter((r) => r.id !== id && r.s !== undefined)
    if (me?.s === undefined || others.length === 0) continue
    const adv = me.s - others.reduce((a, r) => a + r.s!, 0) / others.length
    const extra = me.extraM ?? 0
    base ??= { adv, extra }
    const real = adv - base.adv
    points.push({
      t: f.t,
      s: me.s,
      real,
      ideal: real + (extra - base.extra),
      rank: 1 + others.filter((r) => r.s! > me.s!).length,
    })
  }
  const changes: RankChange[] = []
  for (let i = 1; i < points.length; i++)
    if (points[i].rank !== points[i - 1].rank)
      changes.push({ s: points[i].s, real: points[i].real, from: points[i - 1].rank, to: points[i].rank })
  return { points, changes }
}
