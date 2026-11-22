import { useEffect } from 'react'
import { LANE, LANES, LAP, R, STRAIGHT, trackToWorld, type Vec2 } from '../../trazada/geometry'
import { polyline, range } from '../../trazada/draw'
import { fmtNum, themeColor, themeFont } from '../../trazada/format'
import { startS } from '../../trazada/pruebas'
import type { Race } from '../../trazada/types'
import { useCanvas } from '../../trazada/useCanvas'

type Props = {
  race: Race
  frameIndex: number
  selectedId?: number
  /** Llena el alto de su contenedor en vez de usar 16:9 (para el modal de zoom). */
  fill?: boolean
}

const BAND = LANES * LANE
// Los carriles se dibujan K veces más anchos que en la realidad para distinguir a cada corredor.
const K = 2.5
const HALF_W = STRAIGHT / 2 + R + BAND * K
const HALF_H = R + BAND * K

/**
 * Pista de 400 m vista desde arriba, a escala. Marca el tramo que recorrió el encuadre y
 * dónde está mirando la cámara ahora (/api/zones/) y, si hay datos de atletas, un punto por
 * corredor en su posición (s, d) (/api/athletes/). El elegido va en naranja; el resto, en gris.
 */
export function TopView({ race, frameIndex, selectedId, fill = false }: Props) {
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
    const at = (s: number, d: number) => toScreen(...trackToWorld(s, d * K))
    const lap = range(0, LAP, 0.5)
    const mono = themeFont('mono')

    ctx.clearRect(0, 0, size.w, size.h)

    // Pista como un mapa: carriles en grises alternados (tokens lane-1..8) y líneas blancas.
    for (let lane = 0; lane < LANES; lane++) {
      ctx.fillStyle = themeColor(`lane-${lane + 1}`)
      ctx.beginPath()
      lap.forEach((s, i) => (i ? ctx.lineTo(...at(s, (lane + 1) * LANE)) : ctx.moveTo(...at(s, (lane + 1) * LANE))))
      ctx.closePath()
      lap.forEach((s, i) => (i ? ctx.lineTo(...at(s, lane * LANE)) : ctx.moveTo(...at(s, lane * LANE))))
      ctx.closePath()
      ctx.fill('evenodd')
    }
    ctx.strokeStyle = themeColor('trackline')
    ctx.lineWidth = 1
    for (let lane = 0; lane <= LANES; lane++) polyline(ctx, lap.map((s) => at(s, lane * LANE)))

    // Meta
    ctx.strokeStyle = themeColor('fg')
    ctx.lineWidth = 2
    polyline(ctx, [at(0, 0), at(0, BAND)])
    ctx.font = `500 10px ${mono}`
    ctx.fillStyle = themeColor('muted')
    ctx.textAlign = 'center'
    const [mx, my] = at(0, BAND + 4 / K)
    const distance = race.raw.zones?.distance
    const s0 = distance === undefined ? undefined : startS(distance)
    const startsAtFinish = s0 !== undefined && (s0 < 0.5 || s0 > LAP - 0.5)
    ctx.fillText(startsAtFinish ? 'META · SALIDA' : 'META', mx, my + 6)

    // Línea de salida de la prueba: de ahí parte el grupo.
    if (s0 !== undefined && !startsAtFinish) {
      ctx.strokeStyle = themeColor('fg')
      ctx.lineWidth = 2
      polyline(ctx, [at(s0, 0), at(s0, BAND)])
      const [lx, ly] = at(s0, BAND + 4 / K)
      ctx.textAlign = 'center'
      ctx.fillText(`SALIDA ${fmtNum(distance ?? 0, 0)} m`, lx, ly + 6)
      ctx.textAlign = 'start'
    }

    // Medidas oficiales, discretas
    ctx.font = `500 10px ${mono}`
    ctx.fillStyle = themeColor('muted')
    const [sx, sy] = toScreen(0, -(R - 6))
    ctx.fillText(`recta ${fmtNum(STRAIGHT, 2)} m`, sx, sy)
    const c = toScreen(STRAIGHT / 2, 0)
    const kx = toScreen(STRAIGHT / 2 + R, 0)
    ctx.strokeStyle = themeColor('other')
    ctx.lineWidth = 1
    polyline(ctx, [c, kx])
    ctx.beginPath()
    ctx.arc(c[0], c[1], 2, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillText(`R ${fmtNum(R, 1)} m`, (c[0] + kx[0]) / 2, c[1] - 6)
    ctx.fillText(`${LANES} × ${fmtNum(LANE, 2)} m`, (c[0] + kx[0]) / 2, c[1] + 15)
    ctx.textAlign = 'start'

    // Tramo que recorrió el encuadre durante todo el video: arco de tinta por fuera.
    // (El naranja queda reservado para el corredor elegido.)
    if (race.camera && !race.hasAthletes) {
      const [a0, a1] = race.camera.span
      ctx.save()
      ctx.strokeStyle = themeColor('fg')
      ctx.globalAlpha = 0.3
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      polyline(ctx, range(a0, a1, 0.5).map((s) => at(s, BAND + 2.6 / K)))
      ctx.restore()
    }

    // Dónde mira la cámara en este instante.
    if (frame?.focusS !== undefined && !race.hasAthletes) {
      const [x, y] = at(frame.focusS, BAND / 2)
      ctx.save()
      ctx.fillStyle = themeColor('fg')
      ctx.beginPath()
      ctx.arc(x, y, 6, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = themeColor('surface')
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.restore()
    }

    // Atletas: la posición medida es sólida; la predicha (no se les ve ahora) va tenue.
    const athletes = frame?.athletes ?? []
    const dots = [...athletes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId))
    for (const a of dots) {
      const isSel = a.id === selectedId
      const [x, y] = at(a.s, Math.max(0.3, Math.min(BAND - 0.3, a.d)))
      ctx.save()
      ctx.globalAlpha = a.visible ? 1 : 0.35
      ctx.fillStyle = isSel ? themeColor('pick') : themeColor('other')
      ctx.beginPath()
      ctx.arc(x, y, isSel ? 6 : 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = themeColor('surface')
      ctx.lineWidth = 1.5
      ctx.stroke()
      if (isSel) {
        ctx.font = `600 11px ${mono}`
        ctx.fillStyle = themeColor('fg')
        ctx.textAlign = 'center'
        ctx.fillText(`#${a.id}`, x, y - 11)
        ctx.textAlign = 'start'
      }
      ctx.restore()
    }
  }, [race, frame, size, ref, selectedId])

  return (
    <div className={`relative w-full overflow-hidden ${fill ? 'h-full' : 'aspect-[16/9]'}`}>
      <canvas
        ref={ref}
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label="Vista cenital de la pista de 400 m con el tramo que enfoca la cámara y la posición de cada atleta"
      />
    </div>
  )
}
