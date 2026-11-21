// DATOS FALSOS · único módulo reemplazable.
//
// Simula 5 corredores en la última curva de un 800 m y entrega los datos con
// la MISMA forma que mandarán Andrés (TracksJson) y Daniel (GeometryJson).
// Así el adaptador ya se prueba con el formato real: cuando lleguen los JSON
// de verdad, se borra este archivo y se cambia loadRace() en adapter.ts.

import {
  CURVE,
  MEAS,
  R,
  SEGMENTS,
  STRAIGHT,
  isCurve,
  project,
  solveHomography,
  trackToWorld,
  type Homography,
  type Vec2,
} from '../geometry'
import type { RaceMeta } from '../adapter'
import type { GeometryJson, TracksJson } from '../types'

const VIDEO_W = 1280
const VIDEO_H = 720
const FPS = 15 // igual que fps_out de Andrés
const SUBSTEPS = 4

// Corredores: velocidad (m/s), posición inicial (s) y distancia a la cuerda (d).
const RUNNERS = [
  { id: 1, label: '341', color: '#e5484d', s0: 186.0, v: 6.3, d: 0.35 },
  { id: 2, label: '287', color: '#f5c542', s0: 183.4, v: 6.28, d: 0.35 },
  { id: 3, label: '318', color: '#9b6cf2', s0: 180.8, v: 6.22, d: 0.6 },
  { id: 4, label: '426', color: '#4c8dff', s0: 179.4, v: 6.2, d: 0.35 },
  { id: 5, label: '305', color: '#3dd68c', s0: 179.0, v: 6.6, d: 0.35, hero: true },
]

const [CURVE_IN, CURVE_OUT] = SEGMENTS.curve2
const END_S = CURVE_OUT + 20

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
// El protagonista se abre al entrar a la curva para adelantar y vuelve a la cuerda en la recta.
const heroLane = (s: number) => {
  const out = smooth(CURVE_IN - 6, CURVE_IN + 4, s)
  const back = smooth(CURVE_OUT + 4, CURVE_OUT + 14, s)
  return 0.35 + (1.3 - 0.35) * out * (1 - back)
}

// Cámara de tribuna mirando la curva 2 desde la recta final.
// Se definen 4 puntos del suelo (m) y dónde caen en la imagen (px).
const cx = -STRAIGHT / 2
const H_BASE: Homography = solveHomography(
  [
    [cx + 30, 46],
    [cx - 46, 46],
    [cx - 46, -46],
    [cx + 30, -46],
  ],
  [
    [VIDEO_W * 0.2, VIDEO_H * 0.1],
    [VIDEO_W * 1.0, VIDEO_H * 0.16],
    [VIDEO_W * 1.3, VIDEO_H * 1.2],
    [-VIDEO_W * 0.5, VIDEO_H * 1.08],
  ],
)

// El camarógrafo sigue al grupo con zoom: cada cuadro tiene su propia homografía
// (igual que la que calculará Daniel con una cámara que se mueve).
const ZOOM = 1.9
function followCamera(target: Vec2): Homography {
  // Zoom y desplazamiento en la imagen, aplicados después de H_BASE: H = A · H_BASE
  const [tx, ty] = target
  const a = [ZOOM, 0, VIDEO_W * 0.5 - ZOOM * tx, 0, ZOOM, VIDEO_H * 0.58 - ZOOM * ty, 0, 0, 1]
  const b = H_BASE
  const m = (r: number, c: number) => a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c]
  const out = [m(0, 0), m(0, 1), m(0, 2), m(1, 0), m(1, 1), m(1, 2), m(2, 0), m(2, 1), m(2, 2)]
  return out.map((v) => v / out[8]) as Homography
}

function zoneOf(s: number) {
  // Zonas de Daniel: 2 y 5 rectas; 1-6 y 3-4 mitades de curva. Aquí solo se usan 3, 4 y 5.
  if (s < CURVE_IN) return 2
  if (s < CURVE_IN + CURVE / 2) return 3
  if (s < CURVE_OUT) return 4
  return 5
}

function simulate() {
  const st = RUNNERS.map((r) => ({ ...r, s: r.s0, dNow: r.d, dist: 0, xy: trackToWorld(r.s0, r.d) }))
  const tracksFrames: TracksJson['frames'] = []
  const geoFrames: GeometryJson['frames'] = []
  const dt = 1 / (FPS * SUBSTEPS)
  let step = 0
  let frame = 0
  let aim: Vec2 | null = null

  while (Math.max(...st.map((r) => r.s)) < END_S) {
    for (const r of st) r.dNow = r.hero ? heroLane(r.s) : r.d
    // Bloqueo: si alguien va justo delante en tu misma línea, no puedes ir más rápido que él.
    const vEff = st.map((r) => {
      let v = r.v
      for (const o of st) {
        const gap = o.s - r.s
        if (o !== r && gap > 0 && gap < 1.4 && Math.abs(o.dNow - r.dNow) < 0.6) v = Math.min(v, o.v)
      }
      return v
    })
    st.forEach((r, i) => {
      // En la curva, ir por fuera hace avanzar menos s por cada metro corrido.
      const k = isCurve(r.s) ? (R + MEAS) / (R + r.dNow) : 1
      r.s += vEff[i] * dt * k
      const xy = trackToWorld(r.s, r.dNow)
      r.dist += Math.hypot(xy[0] - r.xy[0], xy[1] - r.xy[1])
      r.xy = xy
    })
    step++
    if (step % SUBSTEPS !== 0) continue

    const t = +(frame / FPS).toFixed(3)
    // El camarógrafo apunta al centro del grupo y se mueve suave (solo mira hacia atrás: causal).
    const groupX = st.reduce((acc, r) => acc + r.xy[0], 0) / st.length
    const groupY = st.reduce((acc, r) => acc + r.xy[1], 0) / st.length
    const target = project(H_BASE, groupX, groupY)
    aim = aim ? [aim[0] + (target[0] - aim[0]) * 0.12, aim[1] + (target[1] - aim[1]) * 0.12] : target
    const H = followCamera(aim)
    tracksFrames.push({
      frame,
      t,
      detections: st.map((r) => {
        const foot = project(H, r.xy[0], r.xy[1])
        const right = project(H, r.xy[0] + 1, r.xy[1])
        const h = Math.max(18, Math.hypot(right[0] - foot[0], right[1] - foot[1]) * 2.4)
        const w = h * 0.38
        return {
          id: r.id,
          bbox: [foot[0] - w / 2, foot[1] - h, foot[0] + w / 2, foot[1]].map((n) => +n.toFixed(1)) as [
            number,
            number,
            number,
            number,
          ],
          foot_px: [+foot[0].toFixed(1), +foot[1].toFixed(1)] as Vec2,
          conf: 0.9,
        }
      }),
    })
    geoFrames.push({
      frame,
      t,
      zone: zoneOf(st.find((r) => r.hero)!.s),
      H,
      runners: st.map((r) => ({
        id: r.id,
        s: +r.s.toFixed(2),
        d: +r.dNow.toFixed(2),
        extra_m: +(r.dist - (r.s - r.s0)).toFixed(2),
      })),
    })
    frame++
  }
  return { tracksFrames, geoFrames }
}

const sim = simulate()
const duration = sim.tracksFrames[sim.tracksFrames.length - 1].t

export const tracks: TracksJson = {
  video: { source: 'simulado', width: VIDEO_W, height: VIDEO_H, fps_out: FPS, frames: sim.tracksFrames.length, duration_s: duration },
  tracks: RUNNERS.map((r) => ({ id: r.id, t_start: 0, t_end: duration, n_obs: sim.tracksFrames.length, on_track: 1 })),
  frames: sim.tracksFrames,
}

// Sin `summary`: así el adaptador calcula los puestos por su cuenta (lo mismo hará con datos reales si falta).
export const geometry: GeometryJson = { frames: sim.geoFrames }

export const meta: RaceMeta = {
  title: '800 m · última curva',
  isMock: true,
  cameraSpan: [CURVE_IN - 25, CURVE_OUT + 30],
  runners: Object.fromEntries(RUNNERS.map((r) => [r.id, { label: r.label, color: r.color, hero: r.hero }])),
}
