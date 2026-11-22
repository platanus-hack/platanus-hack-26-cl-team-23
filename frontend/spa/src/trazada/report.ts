// Informe del atleta: lo que un entrenador quiere saber de UNA carrera de UN atleta.
//
// Todo sale de lo que la API ya entregó: /api/athletes/ (posición y velocidad medidas) y,
// cuando existe, /api/tactics/ (un pronóstico de un modelo, no una medición). Son funciones
// puras sobre `Race`: no piden nada a la red y no inventan datos. Si algo no se vio, se dice.

import { CURVE, LAP, MEAS, R, STRAIGHT } from './geometry'
import type { Race, TacticsResult } from './types'

/** Una medición del atleta (solo cuadros en que se le vio). */
export type Sample = { t: number; x: number; v: number; d: number; s: number; lane: number; rank: number; sigmaX: number }

/** ¿Está esta posición (metros desde la meta, 0-400) dentro de una curva? */
export function inCurve(s: number): boolean {
  const u = ((s % LAP) + LAP) % LAP
  return u < CURVE || (u >= CURVE + STRAIGHT && u < 2 * CURVE + STRAIGHT)
}

/** Metros desde la meta del punto de salida de una prueba (como pruebas.ts). */
const startS = (distance: number) => (((-distance % LAP) + LAP) % LAP) % LAP

/** Posición en la pista (metros desde la meta) de quien lleva `x` m corridos. */
export const sAtX = (x: number, distance: number) => (((startS(distance) + x) % LAP) + LAP) % LAP

/** Distancia de la prueba (la que se usó para medir). */
export const raceDistance = (race: Race) => race.raw.zones?.distance ?? 1500

/** Mediciones de un atleta, ordenadas por tiempo, hasta que cruza la meta. */
export function athleteSeries(race: Race, id: number): Sample[] {
  const distance = raceDistance(race)
  const out: Sample[] = []
  for (const f of race.frames) {
    const a = f.athletes?.find((q) => q.id === id)
    if (!a || !a.visible) continue
    out.push({ t: f.t, x: a.x, v: a.v, d: a.d, s: a.s, lane: a.lane, rank: a.rank, sigmaX: a.sigmaX })
    if (a.x >= distance) break // después de la meta ya no es carrera
  }
  return out
}

/** Atletas vistos en un cuadro que todavía no cruzan la meta. */
function racing(race: Race, frame: Race['frames'][number]) {
  const distance = raceDistance(race)
  return (frame.athletes ?? []).filter((a) => a.visible && a.x < distance)
}

const median = (xs: number[]) => {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

// ---------------------------------------------------------------------------------------------
// Con quién comparar
// ---------------------------------------------------------------------------------------------

/**
 * Rival por defecto: quien iba primero la última vez que se midió al atleta (si él iba
 * primero, el segundo). Así la comparación siempre es "contra el que va adelante".
 */
export function defaultRival(race: Race, id: number): number | undefined {
  for (let i = race.frames.length - 1; i >= 0; i--) {
    const seen = racing(race, race.frames[i])
    if (!seen.some((a) => a.id === id)) continue
    const others = seen.filter((a) => a.id !== id).sort((a, b) => a.rank - b.rank)
    if (others.length) return others[0].id
  }
  return race.runners.find((r) => r.id !== id)?.id
}

// ---------------------------------------------------------------------------------------------
// Parciales: tiempo en cada tramo contra el rival
// ---------------------------------------------------------------------------------------------

/** Cuándo pasó el atleta por los `x` metros: interpola entre las dos mediciones que lo rodean. */
function timeAt(series: Sample[], x: number): { t: number; gap: number } | undefined {
  for (let i = 1; i < series.length; i++) {
    const a = series[i - 1]
    const b = series[i]
    if (a.x <= x && x <= b.x && b.x > a.x) {
      const k = (x - a.x) / (b.x - a.x)
      return { t: a.t + k * (b.t - a.t), gap: b.t - a.t }
    }
  }
  return undefined
}

export type Split = {
  from: number // metros desde la salida
  to: number
  delta: number // s: + el atleta tardó más que el rival (perdió), − tardó menos (ganó)
  t: number // segundo del video en que el atleta empezó el tramo (para saltar ahí)
  estimated: boolean // en ese tramo a alguno de los dos no se le vio: es una interpolación
  curve: number // fracción del tramo que es curva (0-1)
}

/** Si entre dos mediciones pasan más de esto, el tramo es una interpolación, no una medición. */
const SEEN_GAP_S = 1.5

export function splits(race: Race, me: Sample[], rival: Sample[]): { step: number; items: Split[] } {
  const distance = raceDistance(race)
  if (me.length < 2 || rival.length < 2) return { step: 100, items: [] }
  const lo = Math.max(me[0].x, rival[0].x)
  const hi = Math.min(me[me.length - 1].x, rival[rival.length - 1].x)
  const step = hi - lo >= 300 ? 100 : 50
  const items: Split[] = []
  for (let from = Math.ceil(lo / step) * step; from + step <= hi + 1e-6; from += step) {
    const to = from + step
    const a0 = timeAt(me, from)
    const a1 = timeAt(me, to)
    const b0 = timeAt(rival, from)
    const b1 = timeAt(rival, to)
    if (!a0 || !a1 || !b0 || !b1) continue
    let curve = 0
    for (let x = from + 1; x <= to; x += 2) curve += inCurve(sAtX(x, distance)) ? 2 : 0
    items.push({
      from,
      to,
      delta: a1.t - a0.t - (b1.t - b0.t),
      t: a0.t,
      estimated: Math.max(a0.gap, a1.gap, b0.gap, b1.gap) > SEEN_GAP_S,
      curve: Math.min(1, curve / step),
    })
  }
  return { step, items }
}

// ---------------------------------------------------------------------------------------------
// Perfil de velocidad y el sprint final
// ---------------------------------------------------------------------------------------------

export type ProfilePoint = { x: number; v: number }

/** Velocidad media por tramos de `bin` metros (suaviza el ruido de la medición). */
export function speedProfile(series: Sample[], bin = 10): ProfilePoint[] {
  const acc = new Map<number, { sum: number; n: number }>()
  for (const s of series) {
    const k = Math.floor(s.x / bin)
    const e = acc.get(k) ?? { sum: 0, n: 0 }
    e.sum += s.v
    e.n += 1
    acc.set(k, e)
  }
  return [...acc.entries()].sort(([a], [b]) => a - b).map(([k, e]) => ({ x: (k + 0.5) * bin, v: e.sum / e.n }))
}

/**
 * Dónde lanzó el sprint: el primer punto desde el que la velocidad queda, hasta el final de lo
 * medido, al menos un 6 % sobre su ritmo de crucero. Solo se busca en los últimos 500 m.
 * Devuelve los metros que le faltaban a la meta, o nada si no se vio.
 */
export function kickAt(profile: ProfilePoint[], distance: number): number | undefined {
  if (profile.length < 6) return undefined
  const last = profile[profile.length - 1].x
  if (last < distance - 200) return undefined // no se vio el final
  const early = profile.filter((p) => p.x < distance - 500).map((p) => p.v)
  const base = early.length >= 3 ? median(early) : median(profile.slice(0, Math.max(3, profile.length >> 2)).map((p) => p.v))
  let start: number | undefined
  for (let i = profile.length - 1; i >= 0; i--) {
    if (profile[i].v >= base * 1.06) start = profile[i].x
    else break
  }
  if (start === undefined || start < distance - 500 || last - start < 30) return undefined
  return distance - start
}

// ---------------------------------------------------------------------------------------------
// Por dónde corrió: calle y metros de más en cada curva
// ---------------------------------------------------------------------------------------------

export type CurveCost = { x: number; extra: number; seconds: number; t: number }

/**
 * Metros de más por ir por fuera, curva por curva. En una curva, quien corre a `d` m del bordillo
 * recorre (R + d) / (R + MEAS) veces lo que la línea de medición de la calle 1 (igual que la
 * ficha del corredor). Cada vez que entra a una curva empieza una pasada nueva.
 */
export function curveCosts(series: Sample[]): CurveCost[] {
  const out: CurveCost[] = []
  let cur: CurveCost | undefined
  let vSum = 0
  let vN = 0
  for (let i = 1; i < series.length; i++) {
    const a = series[i - 1]
    const b = series[i]
    const dx = b.x - a.x
    const ok = b.t - a.t <= 0.35 && dx > 0 && dx <= 3 // un salto grande es un corte de plano
    if (!inCurve(b.s) || b.x - (cur?.x ?? b.x) > CURVE + 5) {
      if (cur) out.push(cur)
      cur = undefined
      if (!inCurve(b.s)) continue
    }
    if (!cur) cur = { x: b.x, extra: 0, seconds: 0, t: b.t }
    if (!ok) continue
    cur.extra += (dx * (Math.max(MEAS, b.d) - MEAS)) / (R + MEAS)
    vSum += b.v
    vN += 1
  }
  if (cur) out.push(cur)
  const v = vN ? vSum / vN : 6.5
  return out.filter((c) => c.extra > 0.05).map((c) => ({ ...c, seconds: c.extra / v }))
}

export type LaneBand = { from: number; to: number; lane: number }

/** Calle a lo largo de lo medido, en tramos de `bin` metros (la calle más frecuente de cada tramo). */
export function laneBands(series: Sample[], bin = 25): LaneBand[] {
  const acc = new Map<number, number[]>()
  for (const s of series) {
    const k = Math.floor(s.x / bin)
    const l = acc.get(k) ?? []
    l.push(s.lane)
    acc.set(k, l)
  }
  const bands: LaneBand[] = []
  for (const [k, lanes] of [...acc.entries()].sort(([a], [b]) => a - b)) {
    const counts = new Map<number, number>()
    for (const l of lanes) counts.set(l, (counts.get(l) ?? 0) + 1)
    const lane = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0][0]
    const prev = bands[bands.length - 1]
    if (prev && prev.lane === lane && prev.to === k * bin) prev.to = (k + 1) * bin
    else bands.push({ from: k * bin, to: (k + 1) * bin, lane })
  }
  return bands
}

// ---------------------------------------------------------------------------------------------
// Rebufo: ir pegado detrás de otro (mismo criterio que /api/tactics: 0,3–2 m, misma línea)
// ---------------------------------------------------------------------------------------------

export function draftShare(race: Race, id: number): number {
  let seen = 0
  let drafting = 0
  for (const f of race.frames) {
    const all = racing(race, f)
    const me = all.find((a) => a.id === id)
    if (!me) continue
    seen += 1
    if (all.some((o) => o.id !== id && o.x - me.x >= 0.3 && o.x - me.x <= 2 && Math.abs(o.d - me.d) <= 0.7)) drafting += 1
  }
  return seen ? drafting / seen : 0
}

// ---------------------------------------------------------------------------------------------
// Momentos clave
// ---------------------------------------------------------------------------------------------

export type Moment =
  | { kind: 'passed'; t: number; other: number; curve: boolean } // el atleta adelantó a `other`
  | { kind: 'lost'; t: number; other: number; curve: boolean } // `other` adelantó al atleta
  | { kind: 'window'; t: number; other: number; p: number } // pronóstico: ventana para atacar a `other`

/** Para que un cambio de orden cuente, tiene que durar al menos esto (filtra el ruido de la medición). */
const HOLD_S = 1

/** Adelantamientos: cambios de orden con cada rival que se sostienen al menos 1 s antes y después. */
export function passes(race: Race, id: number): Moment[] {
  // por rival: (t, ¿va adelante el rival?, s del atleta) en los cuadros en que se ve a los dos
  const rel = new Map<number, { t: number; ahead: boolean; s: number }[]>()
  for (const f of race.frames) {
    const all = racing(race, f)
    const me = all.find((a) => a.id === id)
    if (!me) continue
    for (const o of all) {
      if (o.id === id) continue
      const l = rel.get(o.id) ?? []
      l.push({ t: f.t, ahead: o.x > me.x, s: me.s })
      rel.set(o.id, l)
    }
  }
  const out: Moment[] = []
  for (const [other, l] of rel) {
    // tramos seguidos con el mismo orden; solo cuentan los que duran HOLD_S
    const runs: { ahead: boolean; t0: number; t1: number; s: number }[] = []
    for (const p of l) {
      const last = runs[runs.length - 1]
      if (last && last.ahead === p.ahead) last.t1 = p.t
      else runs.push({ ahead: p.ahead, t0: p.t, t1: p.t, s: p.s })
    }
    const solid = runs.filter((r) => r.t1 - r.t0 >= HOLD_S)
    for (let i = 1; i < solid.length; i++) {
      const before = solid[i - 1]
      const after = solid[i]
      if (before.ahead === after.ahead) continue
      out.push({ kind: before.ahead ? 'passed' : 'lost', t: after.t0, other, curve: inCurve(after.s) })
    }
  }
  return out.sort((a, b) => a.t - b.t)
}

/** Ventanas de ataque del pronóstico: cada vez que el modelo dice "atacar ya" sobre un rival. */
export function attackWindows(tactics: TacticsResult | undefined, id: number): Moment[] {
  if (!tactics) return []
  const out: Moment[] = []
  let open: number | undefined
  for (const step of tactics.steps) {
    const a = step.attacks.find((q) => q.id === id && q.action === 'attack')
    if (!a) {
      open = undefined
      continue
    }
    if (open === a.rival) continue // la misma ventana sigue abierta
    out.push({ kind: 'window', t: step.t, other: a.rival, p: a.p_attack })
    open = a.rival
  }
  return out
}

/** Reserva de energía estimada del atleta en el tiempo (solo cuando estaba en un duelo). */
export function reserveSeries(tactics: TacticsResult | undefined, id: number) {
  if (!tactics) return []
  return tactics.steps.flatMap((s) => {
    const a = s.attacks.find((q) => q.id === id)
    return a ? [{ t: s.t, reserve: a.reserve, rival: a.rival, rivalReserve: a.rival_reserve, draftM: a.draft_m }] : []
  })
}

// ---------------------------------------------------------------------------------------------
// El informe completo
// ---------------------------------------------------------------------------------------------

export type Advice = { title: string; value: string; detail: string; good: boolean; forecast?: boolean }

export type Report = {
  id: number
  rival: number | undefined
  distance: number
  series: Sample[]
  rank: { start: number; end: number } | undefined
  finished: boolean // se le vio llegar (o casi)
  toGo: number // metros que le faltaban la última vez que se le midió
  splits: { step: number; items: Split[] }
  lost: number // s contra el rival en los tramos comparables (+ perdió)
  curveShare: number // fracción de lo perdido que fue en curvas
  profile: ProfilePoint[]
  rivalProfile: ProfilePoint[]
  kick: number | undefined
  rivalKick: number | undefined
  curves: CurveCost[]
  extraM: number
  extraS: number
  lanes: LaneBand[]
  draft: number
  moments: Moment[]
  reserve: ReturnType<typeof reserveSeries>
  measuredM: number // metros de la prueba en que se le midió
  sigma: number // incertidumbre típica de su posición (m)
  avgV: number
  advice: Advice[]
}

const fmt = (n: number, digits: number) => n.toFixed(digits).replace('.', ',')
const pct = (p: number) => `${Math.round(p * 100)} %`

export function buildReport(race: Race, id: number, rivalId: number | undefined, tactics?: TacticsResult): Report {
  const distance = raceDistance(race)
  const series = athleteSeries(race, id)
  const rivalSeries = rivalId === undefined ? [] : athleteSeries(race, rivalId)
  const sp = splits(race, series, rivalSeries)
  const lost = sp.items.reduce((s, x) => s + x.delta, 0)
  const lostPos = sp.items.filter((x) => x.delta > 0)
  const posSum = lostPos.reduce((s, x) => s + x.delta, 0)
  const curveShare = posSum > 0 ? lostPos.reduce((s, x) => s + x.delta * x.curve, 0) / posSum : 0
  const profile = speedProfile(series)
  const rivalProfile = speedProfile(rivalSeries)
  const curves = curveCosts(series)
  const extraM = curves.reduce((s, c) => s + c.extra, 0)
  const extraS = curves.reduce((s, c) => s + c.seconds, 0)
  const avgV = series.length ? series.reduce((s, x) => s + x.v, 0) / series.length : 0
  const last = series[series.length - 1]
  const bins = new Set(series.map((s) => Math.floor(s.x / 10)))
  const kick = kickAt(profile, distance)
  const rivalKick = kickAt(rivalProfile, distance)
  const draft = draftShare(race, id)
  const windows = attackWindows(tactics, id)
  const done = passes(race, id)
  const moments = [...done, ...windows].sort((a, b) => a.t - b.t)

  const advice: Advice[] = []
  if (extraS >= 0.1 && curves.length) {
    const worst = [...curves].sort((a, b) => b.extra - a.extra)[0]
    advice.push({
      title: 'Correr las curvas más adentro',
      value: `≈ ${fmt(extraS, 2)} s`,
      detail: `Corrió ${fmt(extraM, 1)} m de más por ir por fuera. La curva que más le costó fue la de los ${Math.round(worst.x)} m (+${fmt(worst.extra, 1)} m).`,
      good: false,
    })
  }
  if (kick !== undefined && rivalKick !== undefined && rivalKick - kick >= 20) {
    advice.push({
      title: 'Lanzar el sprint antes',
      value: `${Math.round(rivalKick - kick)} m antes`,
      detail: `Lanzó a falta de ${Math.round(kick)} m; #${rivalId} lo hizo a falta de ${Math.round(rivalKick)} m.`,
      good: false,
    })
  }
  if (draft >= 0.4) {
    advice.push({ title: 'Buen uso del rebufo', value: pct(draft), detail: 'Del tiempo medido, fue protegido detrás de otro. Ahorra energía para el final.', good: true })
  } else if (series.length > 30 && draft < 0.15) {
    advice.push({ title: 'Correr más protegido', value: pct(draft), detail: 'Casi siempre corrió sin nadie adelante a menos de 2 m: gasta más energía que el resto.', good: false })
  }
  const missed = windows.find((w) => !done.some((m) => m.kind === 'passed' && m.other === w.other && m.t >= w.t && m.t - w.t <= 15))
  if (missed && missed.kind === 'window') {
    advice.push({
      title: 'Atacar cuando se abre la ventana',
      value: pct(missed.p),
      detail: `El modelo vio una ventana para pasar a #${missed.other} y no la tomó.`,
      good: false,
      forecast: true,
    })
  }

  return {
    id,
    rival: rivalId,
    distance,
    series,
    rank: series.length ? { start: series[0].rank, end: last.rank } : undefined,
    finished: !!last && last.x >= distance - 5,
    toGo: last ? Math.max(0, distance - last.x) : distance,
    splits: sp,
    lost,
    curveShare,
    profile,
    rivalProfile,
    kick,
    rivalKick,
    curves,
    extraM,
    extraS,
    lanes: laneBands(series),
    draft,
    moments,
    reserve: reserveSeries(tactics, id),
    measuredM: Math.min(distance, bins.size * 10),
    sigma: median(series.map((s) => s.sigmaX)),
    avgV,
    advice,
  }
}

/** Las mediciones del atleta como CSV (coma decimal, así que el separador es punto y coma, como lee Excel en español). */
export function reportCsv(report: Report): string {
  const head = 'segundo;metros_desde_salida;velocidad_m_s;metros_al_bordillo;calle;puesto'
  const rows = report.series.map((s) => [s.t, s.x, s.v, s.d].map((n) => fmt(n, 2)).concat([String(s.lane), String(s.rank)]).join(';'))
  return [head, ...rows].join('\n')
}
