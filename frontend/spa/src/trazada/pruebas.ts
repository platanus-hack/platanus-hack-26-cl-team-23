// Pruebas de pista: cada una sale de un punto distinto del óvalo, porque toda carrera termina
// en la meta. Con la distancia el backend sabe dónde parte el grupo y a qué ritmo.

import { CURVE, LAP, STRAIGHT } from './geometry'

export type Prueba = { distance: number; label: string }

export const PRUEBAS: Prueba[] = [
  { distance: 200, label: '200 m' },
  { distance: 400, label: '400 m' },
  { distance: 800, label: '800 m' },
  { distance: 1000, label: '1000 m' },
  { distance: 1500, label: '1500 m' },
  { distance: 3000, label: '3000 m' },
  { distance: 5000, label: '5000 m' },
  { distance: 10000, label: '10 000 m' },
]

export const DEFAULT_DISTANCE = 1500

/** Metros desde la meta, en sentido de carrera, del punto de salida (0 = en la meta). */
export function startS(distance: number): number {
  return (((-distance % LAP) + LAP) % LAP) % LAP
}

const ZONES: [number, string][] = [
  [CURVE / 2, 'entrada de la curva 1'],
  [CURVE, 'salida de la curva 1'],
  [CURVE + STRAIGHT, 'recta opuesta'],
  [CURVE + STRAIGHT + CURVE / 2, 'entrada de la curva 2'],
  [2 * CURVE + STRAIGHT, 'salida de la curva 2'],
  [LAP, 'recta principal'],
]

/** Frase que dice dónde sale la prueba, para que se vea si calza con el video. */
export function describeStart(distance: number): string {
  const s = startS(distance)
  if (s < 0.5 || s > LAP - 0.5) return 'Sale en la línea de meta.'
  const zone = ZONES.find(([edge]) => s + 1e-6 < edge)?.[1] ?? 'recta principal'
  return `Sale ${Math.round(s)} m después de la meta, en ${zone}.`
}
