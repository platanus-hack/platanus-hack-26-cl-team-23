import { useEffect, useRef } from 'react'
import { pill } from '../../trazada/draw'
import { themeColor, themeFont } from '../../trazada/format'
import { visibleAt } from '../../trazada/adapter'
import type { Race } from '../../trazada/types'
import { useCanvas } from '../../trazada/useCanvas'

type Props = {
  race: Race
  frameIndex: number
  t: number
  playing: boolean
  showOverlay: boolean
  selectedId: number | undefined
  onSelect: (id: number) => void
}

/**
 * El video con la capa del detector encima: una caja y una etiqueta por corredor,
 * dibujadas en píxeles del video y escaladas al tamaño de la pantalla.
 */
export function CameraView({ race, frameIndex, t, playing, showOverlay, selectedId, onSelect }: Props) {
  const { ref, size } = useCanvas()
  const videoRef = useRef<HTMLVideoElement>(null)
  const frame = race.frames[frameIndex]

  // Mantenemos el video sincronizado con el reloj de la pantalla.
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
    ctx.clearRect(0, 0, size.w, size.h)
    if (!showOverlay || !frame) return

    const k = size.w / race.video.width // px de video → px de pantalla
    const info = new Map(race.runners.map((r) => [r.id, r]))
    const mono = themeFont('mono')
    const pick = themeColor('pick')
    // Detecciones de ahora + las recién perdidas, para que no parpadeen.
    const visible = visibleAt(race.frames, frameIndex)

    // Cajas: solo las esquinas, para no tapar al corredor.
    for (const r of visible) {
      const [x1, y1, x2, y2] = r.bbox.map((n) => n * k)
      const isSel = r.id === selectedId
      const c = Math.min(10, (x2 - x1) / 3)
      ctx.strokeStyle = isSel ? pick : 'rgba(255,255,255,.6)'
      ctx.lineWidth = isSel ? 2 : 1.2
      ctx.globalAlpha = r.stale ? 0.5 : 1
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
      ctx.globalAlpha = 1
    }

    // Etiqueta con el id del corredor. El elegido va primero para que quede en su lugar;
    // si dos etiquetas chocan, la siguiente sube un escalón.
    const placed: { x: number; y: number }[] = []
    const labeled = [...visible].sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId))
    for (const r of labeled) {
      const isSel = r.id === selectedId
      const cx = ((r.bbox[0] + r.bbox[2]) / 2) * k
      let y = r.bbox[1] * k - 14
      while (placed.some((p) => Math.abs(p.x - cx) < 44 && Math.abs(p.y - y) < 22)) y -= 22
      placed.push({ x: cx, y })
      pill(ctx, info.get(r.id)?.label ?? `#${r.id}`, cx, y, {
        font: `${isSel ? 700 : 500} ${isSel ? 13 : 11}px ${mono}`,
        color: isSel ? themeColor('hero') : 'rgba(255,255,255,.8)',
        swatch: isSel ? pick : undefined,
      })
    }
  }, [race, frame, frameIndex, showOverlay, selectedId, size, ref])

  // Clic sobre un corredor → elegirlo.
  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!frame) return
    const rect = e.currentTarget.getBoundingClientRect()
    const k = rect.width / race.video.width
    const x = (e.clientX - rect.left) / k
    const y = (e.clientY - rect.top) / k
    const pad = 14 / k
    const hit = visibleAt(race.frames, frameIndex)
      .map((r) => {
        const [x1, y1, x2, y2] = r.bbox
        const inside = x >= x1 - pad && x <= x2 + pad && y >= y1 - pad && y <= y2 + pad
        const dist = Math.hypot(x - (x1 + x2) / 2, y - (y1 + y2) / 2)
        return { id: r.id, inside, dist }
      })
      .filter((h) => h.inside)
      .sort((a, b) => a.dist - b.dist)[0]
    if (hit) onSelect(hit.id)
  }

  return (
    // El contenedor toma la proporción exacta del video: así las cajas, que vienen en
    // píxeles del original, calzan también con videos verticales de celular.
    <div
      className="relative mx-auto max-h-[70svh] w-full overflow-hidden bg-black"
      style={{ aspectRatio: `${race.video.width} / ${race.video.height}` }}
    >
      {race.video.url && (
        <video
          ref={videoRef}
          src={race.video.url}
          muted
          playsInline
          preload="auto"
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}
      <canvas
        ref={ref}
        onClick={handleClick}
        className="absolute inset-0 h-full w-full cursor-crosshair"
        role="img"
        aria-label="Video con los corredores detectados"
      />
    </div>
  )
}
