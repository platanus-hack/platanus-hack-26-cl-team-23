import { useEffect, useRef } from 'react'
import { LANE, LANES, MEAS, project, trackToWorld, type Homography, type Vec2 } from '../../trazada/geometry'
import { pill, polygon, polyline, range } from '../../trazada/draw'
import { fmtMeters, themeColor, themeFont } from '../../trazada/format'
import { visibleAt } from '../../trazada/adapter'
import type { Race } from '../../trazada/types'
import { useCanvas } from '../../trazada/useCanvas'

type Props = {
  race: Race
  frameIndex: number
  t: number
  playing: boolean
  showOverlay: boolean
  showGhost: boolean
  selectedId: number | undefined
  onSelect: (id: number) => void
}

const TRAIL_SECONDS = 6

/**
 * Vista de la cámara. Aquí va el video (grabado o transmisión en vivo);
 * mientras no haya video, se dibuja una pista simulada de fondo.
 * Encima, una capa en canvas con trayectorias, la cuerda y los metros extra.
 * Todo se calcula en píxeles del video y se escala al tamaño de la pantalla.
 */
export function CameraView({ race, frameIndex, t, playing, showOverlay, showGhost, selectedId, onSelect }: Props) {
  const { ref, size } = useCanvas()
  const videoRef = useRef<HTMLVideoElement>(null)
  const frame = race.frames[frameIndex]

  // Video real: lo mantenemos sincronizado con el reloj de la pantalla.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    // En pausa (o moviendo la línea de tiempo) seguimos el reloj al cuadro;
    // reproduciendo, solo corregimos si se desfasa harto, para que el video no tartamudee.
    if (Math.abs(v.currentTime - t) > (playing ? 0.4 : 0.05)) v.currentTime = t
    if (playing && v.paused) void v.play().catch(() => {})
    if (!playing && !v.paused) v.pause()
  }, [t, playing])

  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx || size.w === 0) return
    const k = size.w / race.video.width // px de video → px de pantalla
    const H = frame?.worldToImage
    const toScreen = (H: Homography, x: number, y: number): Vec2 => {
      const [u, v] = project(H, x, y)
      return [u * k, v * k]
    }
    const info = new Map(race.runners.map((r) => [r.id, r]))
    const mono = themeFont('mono')
    const pick = themeColor('pick')
    ctx.clearRect(0, 0, size.w, size.h)

    // ---- Fondo simulado (solo si no hay video) ----
    if (!race.video.url) {
      const sky = ctx.createLinearGradient(0, 0, 0, size.h)
      sky.addColorStop(0, '#16261d')
      sky.addColorStop(1, themeColor('grass2'))
      ctx.fillStyle = sky
      ctx.fillRect(0, 0, size.w, size.h)
      if (H && race.cameraSpan) {
        const [s0, s1] = race.cameraSpan
        const ss = range(s0 - 40, s1 + 40, 1)
        const outer = ss.map((s) => toScreen(H, ...trackToWorld(s, LANES * LANE)))
        const inner = ss.map((s) => toScreen(H, ...trackToWorld(s, 0)))
        ctx.fillStyle = themeColor('track')
        polygon(ctx, [...outer, ...inner.reverse()])
        ctx.strokeStyle = themeColor('trackline')
        ctx.globalAlpha = 0.7
        for (let lane = 0; lane <= LANES; lane++) {
          ctx.lineWidth = lane === 0 ? 2 : 1
          polyline(ctx, ss.map((s) => toScreen(H, ...trackToWorld(s, lane * LANE))))
        }
        ctx.globalAlpha = 1
      }
      const sorted = [...(frame?.runners ?? [])].sort((a, b) => (a.footPx?.[1] ?? 0) - (b.footPx?.[1] ?? 0))
      for (const r of sorted) {
        if (!r.bbox) continue
        const [x1, y1, x2, y2] = r.bbox.map((n) => n * k)
        drawFigure(ctx, x1, y1, x2, y2, info.get(r.id)?.color ?? '#ccc', info.get(r.id)?.label ?? '')
      }
      // viñeta, como un lente real
      const vg = ctx.createRadialGradient(size.w / 2, size.h / 2, size.h * 0.35, size.w / 2, size.h / 2, size.w * 0.75)
      vg.addColorStop(0, 'rgba(0,0,0,0)')
      vg.addColorStop(1, 'rgba(0,0,0,.45)')
      ctx.fillStyle = vg
      ctx.fillRect(0, 0, size.w, size.h)
    }

    if (!showOverlay || !frame) return
    // Lo que se dibuja encima: detecciones actuales + las recién perdidas (evita parpadeo)
    const visible = visibleAt(race.frames, frameIndex)

    // ---- Capa aumentada ----
    // 1. Cuerda: la línea de medición. Es el camino más corto posible.
    if (H && race.cameraSpan) {
      const [s0, s1] = race.cameraSpan
      ctx.save()
      ctx.setLineDash([8, 7])
      ctx.strokeStyle = 'rgba(255,255,255,.9)'
      ctx.lineWidth = 2
      ctx.shadowColor = 'rgba(0,0,0,.6)'
      ctx.shadowBlur = 4
      polyline(ctx, range(s0 - 40, s1 + 40, 1).map((s) => toScreen(H, ...trackToWorld(s, MEAS))))
      ctx.restore()
    }

    // 2. Trayectorias: solo cuadros pasados (causal). El elegido en verde, el resto en blanco tenue.
    // Sin homografía los píxeles viejos se corren si la cámara se mueve: cola más corta.
    const from = frame.t - (H ? TRAIL_SECONDS : 1.5)
    const history = race.frames.slice(0, frameIndex + 1).filter((f) => f.t >= from)
    // Sin homografía no hay forma de corregir el movimiento de la cámara: la cola en píxeles
    // se convierte en garabatos. En ese caso no dibujamos trayectorias.
    const ordered = (H ? [...frame.runners] : []).sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId))
    for (const r of ordered) {
      const isSel = r.id === selectedId
      // Si la cámara se mueve, los píxeles de cuadros pasados ya no calzan con la imagen actual.
      // Por eso, si tenemos posición en metros (s, d), la reproyectamos con la homografía de AHORA.
      const pts = history
        .map((f) => {
          const p = f.runners.find((x) => x.id === r.id)
          if (!p) return undefined
          if (H && p.s !== undefined && p.d !== undefined) return toScreen(H, ...trackToWorld(p.s, p.d))
          return p.footPx ? ([p.footPx[0] * k, p.footPx[1] * k] as Vec2) : undefined
        })
        .filter((p): p is Vec2 => !!p)
      if (pts.length < 2) continue
      ctx.save()
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      if (isSel) {
        ctx.shadowColor = pick
        ctx.shadowBlur = 10
      }
      ctx.strokeStyle = isSel ? pick : 'rgba(255,255,255,.45)'
      ctx.lineWidth = isSel ? 4 : 1.6
      polyline(ctx, pts)
      ctx.restore()
    }

    // 3. Fantasma: dónde iría el elegido si esos metros extra los hubiera corrido por la cuerda.
    const sel = frame.runners.find((r) => r.id === selectedId)
    if (showGhost && H && sel?.s !== undefined && (sel.extraM ?? 0) > 0.3) {
      const [gx, gy] = trackToWorld(sel.s + sel.extraM!, MEAS)
      const [x, y] = toScreen(H, gx, gy)
      const [x2, y2] = toScreen(H, gx + 1, gy)
      const h = Math.max(16, Math.hypot(x2 - x, y2 - y) * 2.4)
      ctx.save()
      ctx.setLineDash([3, 3])
      ctx.strokeStyle = pick
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.ellipse(x, y, h * 0.32, h * 0.1, 0, 0, Math.PI * 2)
      ctx.stroke()
      ctx.beginPath()
      ctx.roundRect(x - h * 0.19, y - h, h * 0.38, h, h * 0.15)
      ctx.stroke()
      ctx.restore()
    }

    // Cajas del detector (solo con video real): esquinas finas, para no tapar al corredor.
    if (race.video.url) {
      for (const r of visible) {
        if (!r.bbox) continue
        const [x1, y1, x2, y2] = r.bbox.map((n) => n * k)
        const isSel = r.id === selectedId
        const c = Math.min(10, (x2 - x1) / 3)
        ctx.strokeStyle = isSel ? pick : 'rgba(255,255,255,.6)'
        ctx.lineWidth = isSel ? 2 : 1.2
        ctx.beginPath()
        for (const [cx0, cy0, dx, dy] of [
          [x1, y1, 1, 1],
          [x2, y1, -1, 1],
          [x1, y2, 1, -1],
          [x2, y2, -1, -1],
        ]) {
          ctx.moveTo(cx0 + dx * c, cy0)
          ctx.lineTo(cx0, cy0)
          ctx.lineTo(cx0, cy0 + dy * c)
        }
        ctx.stroke()
      }
    }

    // 4. Etiqueta "+x m" sobre cada corredor (o su ID, si todavía no hay metros). El elegido va primero para que quede en su lugar;
    //    si dos etiquetas chocan, la siguiente sube un escalón.
    const placed: { x: number; y: number }[] = []
    const labeled = visible
      .filter((r) => r.bbox)
      .sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId))
    for (const r of labeled) {
      const isSel = r.id === selectedId
      const meta = info.get(r.id)
      const cx = ((r.bbox![0] + r.bbox![2]) / 2) * k
      let y = r.bbox![1] * k - 14
      while (placed.some((p) => Math.abs(p.x - cx) < (r.extraM !== undefined ? 80 : 44) && Math.abs(p.y - y) < 22)) y -= 22
      placed.push({ x: cx, y })
      const metric = r.extraM !== undefined ? fmtMeters(r.extraM) : undefined
      const text = metric ? (isSel ? `${meta?.label} ${metric}` : metric) : (meta?.label ?? `#${r.id}`)
      pill(ctx, text, cx, y, {
        font: `${isSel ? 700 : 500} ${isSel ? 13 : 11}px ${mono}`,
        color: isSel ? themeColor('hero') : 'rgba(255,255,255,.8)',
        swatch: isSel ? pick : undefined,
      })
    }
  }, [race, frame, frameIndex, showOverlay, showGhost, selectedId, size, ref])

  // Clic sobre un corredor → elegirlo.
  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!frame) return
    const rect = e.currentTarget.getBoundingClientRect()
    const k = rect.width / race.video.width
    const x = (e.clientX - rect.left) / k
    const y = (e.clientY - rect.top) / k
    const pad = 14 / k
    const hit = visibleAt(race.frames, frameIndex)
      .filter((r) => r.bbox)
      .map((r) => {
        const [x1, y1, x2, y2] = r.bbox!
        const inside = x >= x1 - pad && x <= x2 + pad && y >= y1 - pad && y <= y2 + pad
        const dist = Math.hypot(x - (x1 + x2) / 2, y - (y1 + y2) / 2)
        return { id: r.id, inside, dist }
      })
      .filter((h) => h.inside)
      .sort((a, b) => a.dist - b.dist)[0]
    if (hit) onSelect(hit.id)
  }

  return (
    <div className="relative aspect-video w-full overflow-hidden bg-grass2">
      {race.video.url && (
        <video
          ref={videoRef}
          src={race.video.url}
          muted
          playsInline
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
      <canvas
        ref={ref}
        onClick={handleClick}
        className="absolute inset-0 h-full w-full cursor-crosshair"
        role="img"
        aria-label="Vista de la cámara con las trayectorias de cada corredor, la cuerda y los metros extra. Haz clic en un corredor para elegirlo."
      />
    </div>
  )
}

/** Silueta simple de corredor dentro de su caja (solo para el video simulado). */
function drawFigure(
  ctx: CanvasRenderingContext2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  color: string,
  label: string,
) {
  const h = y2 - y1
  const w = x2 - x1
  const x = (x1 + x2) / 2
  ctx.fillStyle = 'rgba(0,0,0,.3)'
  ctx.beginPath()
  ctx.ellipse(x, y2, w * 0.75, w * 0.22, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#2a2f38'
  ctx.fillRect(x - w * 0.36, y2 - h * 0.45, w * 0.28, h * 0.45)
  ctx.fillRect(x + w * 0.08, y2 - h * 0.45, w * 0.28, h * 0.45)
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.roundRect(x - w * 0.4, y2 - h * 0.86, w * 0.8, h * 0.44, w * 0.2)
  ctx.fill()
  ctx.fillStyle = '#e6b89c'
  ctx.beginPath()
  ctx.arc(x, y1 + h * 0.07, w * 0.26, 0, Math.PI * 2)
  ctx.fill()
  if (label && h > 40) {
    ctx.fillStyle = '#fff'
    ctx.fillRect(x - w * 0.3, y2 - h * 0.76, w * 0.6, h * 0.15)
    ctx.fillStyle = '#111'
    ctx.font = `700 ${Math.max(7, h * 0.12)}px ${themeFont('mono')}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, x, y2 - h * 0.68)
    ctx.textAlign = 'start'
    ctx.textBaseline = 'alphabetic'
  }
}
