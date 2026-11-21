// Geometría oficial de una pista de 400 m (World Athletics).
//
// Sistema de coordenadas "mundo" (metros, vista desde arriba):
//   - origen en el centro del óvalo, x a lo largo de las rectas, y hacia la recta opuesta.
//   - la recta final (donde está la meta) queda en y < 0 y se corre hacia +x.
//   - sentido de carrera: antihorario.
// Una posición en la pista se describe como (s, d):
//   s = metros recorridos por la línea de medición desde la meta (0..400)
//   d = distancia lateral a la cuerda (el bordillo interior), en metros

export const R = 36.5 // radio interior (cuerda)
export const LANE = 1.22 // ancho de cada pista
export const LANES = 8
export const MEAS = 0.3 // la línea de medición va 0,30 m por fuera de la cuerda en la pista 1
export const CURVE = Math.PI * (R + MEAS) // 115,61 m por curva
export const STRAIGHT = 84.39 // largo de cada recta
export const LAP = 2 * CURVE + 2 * STRAIGHT // = 400,0 m

export type Vec2 = [number, number]

/** Convierte (s, d) en coordenadas mundo (x, y) en metros. */
export function trackToWorld(s: number, d: number): Vec2 {
  const u = ((s % LAP) + LAP) % LAP
  const r = R + d
  const half = STRAIGHT / 2
  if (u < CURVE) {
    // curva 1, centro en (+half, 0), de abajo hacia arriba
    const a = -Math.PI / 2 + u / (R + MEAS)
    return [half + r * Math.cos(a), r * Math.sin(a)]
  }
  if (u < CURVE + STRAIGHT) {
    // recta opuesta, hacia -x
    return [half - (u - CURVE), r]
  }
  if (u < 2 * CURVE + STRAIGHT) {
    // curva 2, centro en (-half, 0), de arriba hacia abajo
    const a = Math.PI / 2 + (u - CURVE - STRAIGHT) / (R + MEAS)
    return [-half + r * Math.cos(a), r * Math.sin(a)]
  }
  // recta final, hacia +x hasta la meta
  return [-half + (u - 2 * CURVE - STRAIGHT), -r]
}
