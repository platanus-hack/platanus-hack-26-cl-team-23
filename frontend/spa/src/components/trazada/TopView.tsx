import { useEffect } from 'react'
import { LANE, LANES, LAP, R, STRAIGHT, trackToWorld, type Vec2 } from '../../trazada/geometry'
import { polygon, polyline, range } from '../../trazada/draw'
import { fmtNum, themeColor, themeFont } from '../../trazada/format'
import type { Race } from '../../trazada/types'
import { useCanvas } from '../../trazada/useCanvas'

type Props = {
  race: Race
  frameIndex: number
}

const BAND = LANES * LANE
const HALF_W = STRAIGHT / 2 + R + BAND
const HALF_H = R + BAND

/**
 * Pista de 400 m vista desde arriba, a escala. Marca el tramo que recorrió el encuadre y
 * dónde está mirando la cámara ahora. Todo eso sale de /api/zones/: no hay posiciones de
 * corredores porque el backend todavía no las calcula.
 */
export function TopView({ race, frameIndex }: Props) {
  const { ref, size } = useCanvas()
  const frame = race.frames[frameIndex]

  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx || size.w === 0) return
    const pad = 20
    const scale = Math.min((size.w - 2 * pad) / (2 * HALF_W), (size.h - 2 * pad) / (2 * HALF_H))
    const ox = size.w / 2
    const oy = size.h / 2
    const toScreen = (x: number, y: number): Vec2 => [ox + x * scale, oy - y * scale]
    const at = (s: number, d: number) => toScreen(...trackToWorld(s, d))
    const lap = range(0, LAP, 0.5)
    const mono = themeFont('mono')
    const sans = themeFont('sans')
    const accent = themeColor('accent')

    ctx.clearRect(0, 0, size.w, size.h)

    // Pista en tonos apagados: los datos son lo único que debe gritar.
    ctx.fillStyle = '#17271e'
    polygon(ctx, lap.map((s) => at(s, 0)))
    ctx.fillStyle = '#47291f'
    ctx.beginPath()
    lap.forEach((s, i) => (i ? ctx.lineTo(...at(s, BAND)) : ctx.moveTo(...at(s, BAND))))
    ctx.closePath()
    lap.forEach((s, i) => (i ? ctx.lineTo(...at(s, 0)) : ctx.moveTo(...at(s, 0))))
    ctx.closePath()
    ctx.fill('evenodd')
    ctx.strokeStyle = 'rgba(243,233,226,.16)'
    ctx.lineWidth = 0.8
    for (let lane = 1; lane < LANES; lane++) polyline(ctx, lap.map((s) => at(s, lane * LANE)))
    ctx.strokeStyle = 'rgba(243,233,226,.5)'
    ctx.lineWidth = 1
    polyline(ctx, lap.map((s) => at(s, 0)))
    polyline(ctx, lap.map((s) => at(s, BAND)))

    // Meta
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 2
    polyline(ctx, [at(0, 0), at(0, BAND)])
    ctx.font = `700 10px ${sans}`
    ctx.fillStyle = themeColor('muted')
    ctx.textAlign = 'center'
    const [mx, my] = at(0, BAND + 4)
    ctx.fillText('META', mx, my + 6)

    // Medidas oficiales, discretas
    ctx.font = `500 10px ${mono}`
    ctx.fillStyle = 'rgba(138,151,169,.85)'
    const [sx, sy] = toScreen(0, -(R - 6))
    ctx.fillText(`recta ${fmtNum(STRAIGHT, 2)} m`, sx, sy)
    const c = toScreen(STRAIGHT / 2, 0)
    const kx = toScreen(STRAIGHT / 2 + R, 0)
    ctx.strokeStyle = 'rgba(138,151,169,.5)'
    ctx.lineWidth = 1
    polyline(ctx, [c, kx])
    ctx.beginPath()
    ctx.arc(c[0], c[1], 2, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillText(`R ${fmtNum(R, 1)} m`, (c[0] + kx[0]) / 2, c[1] - 6)
    ctx.fillText(`${LANES} × ${fmtNum(LANE, 2)} m`, (c[0] + kx[0]) / 2, c[1] + 15)
    ctx.textAlign = 'start'

    // Tramo que recorrió el encuadre durante todo el video: arco naranja por fuera.
    if (race.camera) {
      const [s0, s1] = race.camera.span
      ctx.save()
      ctx.strokeStyle = accent
      ctx.globalAlpha = 0.35
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      polyline(ctx, range(s0, s1, 0.5).map((s) => at(s, BAND + 2.6)))
      ctx.restore()
    }

    // Dónde mira la cámara en este instante.
    if (frame?.focusS !== undefined) {
      const [x, y] = at(frame.focusS, BAND / 2)
      ctx.save()
      ctx.fillStyle = accent
      ctx.beginPath()
      ctx.arc(x, y, 6, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = themeColor('panel')
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.restore()
    }
  }, [race, frame, size, ref])

  return (
    <div className="relative aspect-[16/9] w-full overflow-hidden">
      <canvas
        ref={ref}
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label="Vista cenital de la pista de 400 m con el tramo que enfoca la cámara"
      />
    </div>
  )
}
