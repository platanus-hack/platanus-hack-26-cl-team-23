import { useEffect, useRef } from 'react'
import { LANE, LANES, LAP, MEAS, R, STRAIGHT, trackToWorld, type Vec2 } from '../../trazada/geometry'
import { polygon, polyline, range } from '../../trazada/draw'
import { fmtNum, themeColor, themeFont } from '../../trazada/format'
import type { Race } from '../../trazada/types'
import { useCanvas } from '../../trazada/useCanvas'

type Props = {
  race: Race
  frameIndex: number
  showGhost: boolean
  selectedId: number | undefined
  onSelect: (id: number) => void
}

const BAND = LANES * LANE
const HALF_W = STRAIGHT / 2 + R + BAND
const HALF_H = R + BAND

/** Pista de 400 m vista desde arriba, a escala, con las medidas oficiales. */
export function TopView({ race, frameIndex, showGhost, selectedId, onSelect }: Props) {
  const { ref, size } = useCanvas()
  const frame = race.frames[frameIndex]
  // Guardamos dónde quedó dibujado cada corredor para saber a quién se le hizo clic.
  const dots = useRef<{ id: number; x: number; y: number }[]>([])

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
    const pick = themeColor('pick')
    const panel = themeColor('panel')

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

    // Tramo que mira la cámara: arco naranja por fuera de la pista.
    if (race.cameraSpan) {
      const [s0, s1] = race.cameraSpan
      ctx.save()
      ctx.strokeStyle = themeColor('accent')
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      polyline(ctx, range(s0, s1, 0.5).map((s) => at(s, BAND + 2.6)))
      ctx.restore()
    }

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

    if (!frame) return
    const past = race.frames.slice(0, frameIndex + 1)
    const ids = frame.runners.map((r) => r.id).sort((a, b) => Number(a === selectedId) - Number(b === selectedId))

    // Trayectorias: el elegido en verde, el resto en gris
    for (const id of ids) {
      const isSel = id === selectedId
      const pts = past
        .map((f) => f.runners.find((x) => x.id === id))
        .filter((x) => x?.s !== undefined && x?.d !== undefined)
        .map((x) => at(x!.s!, x!.d!))
      ctx.strokeStyle = isSel ? pick : 'rgba(170,180,195,.4)'
      ctx.lineWidth = isSel ? 2.5 : 1.2
      ctx.lineCap = 'round'
      polyline(ctx, pts)
    }

    // Fantasma: dónde iría el elegido si hubiera corrido esos metros por la cuerda
    const sel = frame.runners.find((r) => r.id === selectedId)
    if (showGhost && sel?.s !== undefined && (sel.extraM ?? 0) > 0.3) {
      const [gx, gy] = at(sel.s + sel.extraM!, MEAS)
      ctx.save()
      ctx.setLineDash([2, 2])
      ctx.strokeStyle = pick
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(gx, gy, 5.5, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()
    }

    // Corredores, con un anillo del color del panel para que no se pierdan al cruzarse
    dots.current = []
    for (const id of ids) {
      const r = frame.runners.find((x) => x.id === id)!
      if (r.s === undefined || r.d === undefined) continue
      const isSel = id === selectedId
      const [x, y] = at(r.s, r.d)
      dots.current.push({ id, x, y })
      ctx.beginPath()
      ctx.arc(x, y, isSel ? 5.5 : 4, 0, Math.PI * 2)
      ctx.fillStyle = isSel ? pick : themeColor('other')
      ctx.fill()
      ctx.lineWidth = 2
      ctx.strokeStyle = panel
      ctx.stroke()
    }
  }, [race, frame, frameIndex, showGhost, selectedId, size, ref])

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const best = dots.current
      .map((d) => ({ id: d.id, dist: Math.hypot(d.x - x, d.y - y) }))
      .sort((a, b) => a.dist - b.dist)[0]
    if (best && best.dist < 18) onSelect(best.id)
  }

  return (
    <div className="relative aspect-[16/9] w-full overflow-hidden">
      <canvas
        ref={ref}
        onClick={handleClick}
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label="Vista cenital de la pista de 400 m con la posición de cada corredor"
      />
    </div>
  )
}
