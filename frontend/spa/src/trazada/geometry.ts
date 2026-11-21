// Geometría oficial de una pista de 400 m (World Athletics) y utilidades de proyección.
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

// Tramos en orden de carrera, empezando en la meta.
export const SEGMENTS = {
  curve1: [0, CURVE],
  backStraight: [CURVE, CURVE + STRAIGHT],
  curve2: [CURVE + STRAIGHT, 2 * CURVE + STRAIGHT],
  homeStraight: [2 * CURVE + STRAIGHT, LAP],
} as const

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

export const isCurve = (s: number) => {
  const u = ((s % LAP) + LAP) % LAP
  return u < CURVE || (u >= CURVE + STRAIGHT && u < 2 * CURVE + STRAIGHT)
}

// ---------- Homografía ----------
// Una homografía es una matriz 3x3 que lleva puntos de un plano a otro plano.
// Aquí: del suelo de la pista (metros) a la imagen de la cámara (píxeles).
// Es lo que Daniel calcula por cuadro; con ella podemos dibujar la cuerda encima del video.

export type Homography = [number, number, number, number, number, number, number, number, number]

export function project(H: Homography, x: number, y: number): Vec2 {
  const w = H[6] * x + H[7] * y + H[8]
  return [(H[0] * x + H[1] * y + H[2]) / w, (H[3] * x + H[4] * y + H[5]) / w]
}

/** Resuelve la homografía exacta que lleva 4 puntos src a 4 puntos dst. */
export function solveHomography(src: Vec2[], dst: Vec2[]): Homography {
  const A: number[][] = []
  const b: number[] = []
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i]
    const [u, v] = dst[i]
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y])
    b.push(u)
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y])
    b.push(v)
  }
  for (let c = 0; c < 8; c++) {
    let m = c
    for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[m][c])) m = r
    ;[A[c], A[m]] = [A[m], A[c]]
    ;[b[c], b[m]] = [b[m], b[c]]
    for (let r = 0; r < 8; r++) {
      if (r === c) continue
      const f = A[r][c] / A[c][c]
      for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k]
      b[r] -= f * b[c]
    }
  }
  const h = b.map((bi, i) => bi / A[i][i])
  return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1]
}
