// Tácticas: pronóstico del final (P de ganar, de podio, llegada) y mejores momentos para adelantar.
//
// Sale de POST /api/tactics/, que trabaja sobre lo que ya midió /api/athletes/. Es un modelo con
// parámetros supuestos, no una medición: la pantalla siempre lo rotula como pronóstico. Es un extra
// que se pide DESPUÉS de mostrar la carrera, así que no hace esperar al video.

import { useEffect, useState } from 'react'
import { apiPost } from '../lib/api'
import { CURVE, LAP, STRAIGHT } from './geometry'
import type { Race, TacticsResult, TacticsStep } from './types'

/** Cuerpo de la petición a partir de las respuestas originales de la API. */
export function tacticsRequest(race: Race) {
  const athletes = race.raw.athletes
  if (!athletes) return undefined
  return {
    source: 'upload',
    distance: race.raw.zones?.distance ?? 1500,
    t0: athletes.t0,
    every_s: 1,
    frames: athletes.frames.map((f) => ({
      t: f.t,
      athletes: f.athletes
        .filter((a) => a.visible)
        .map((a) => ({ id: a.id, x: a.x, v: a.v, d: a.d, sigma_x: a.sigma_x })),
    })),
  }
}

export type TacticsState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; result: TacticsResult }
  | { kind: 'error' }

/** Pide las tácticas de una carrera. Si falla, la pantalla sigue igual: es un extra. */
export function useTactics(race: Race): TacticsState {
  const body = tacticsRequest(race)
  const [state, setState] = useState<TacticsState>(body ? { kind: 'loading' } : { kind: 'idle' })

  useEffect(() => {
    if (!body) return
    const ctrl = new AbortController()
    apiPost<TacticsResult>('/tactics/', body, { signal: ctrl.signal })
      .then((result) => setState({ kind: 'ready', result }))
      .catch(() => !ctrl.signal.aborted && setState({ kind: 'error' }))
    return () => ctrl.abort()
    // La carrera no cambia dentro de la pantalla (Home la reemplaza con `key`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [race.video.url])

  return state
}

/** El pronóstico vigente en el instante `t` del video: el último que ya se calculó. */
export function stepAt(steps: TacticsStep[], t: number): TacticsStep | undefined {
  let found: TacticsStep | undefined
  for (const s of steps) {
    if (s.t > t) break
    found = s
  }
  return found ?? steps[0]
}

/** ¿Está esta posición (metros desde la meta, 0-400) dentro de una curva? */
const inCurve = (s: number) => s < CURVE || (s >= CURVE + STRAIGHT && s < 2 * CURVE + STRAIGHT)

/** Posición en la pista (s, desde la meta) de quien tiene que correr `remaining` m para terminar. */
const posAt = (remaining: number) => (((LAP - remaining) % LAP) + LAP) % LAP

/**
 * Tramos de curva y de recta en los `span` metros que le faltan a un atleta hasta la meta.
 * Devuelve [desde, hasta, esCurva] en metros que faltan (de mayor a menor).
 */
export function remainingSegments(span: number): [number, number, boolean][] {
  const out: [number, number, boolean][] = []
  const step = 2
  let from = span
  let curve = inCurve(posAt(span))
  for (let r = span - step; r >= -1e-9; r -= step) {
    const c = inCurve(posAt(Math.max(r, 0)))
    if (c !== curve) {
      out.push([from, r + step, curve])
      from = r + step
      curve = c
    }
  }
  out.push([from, 0, curve])
  return out
}
