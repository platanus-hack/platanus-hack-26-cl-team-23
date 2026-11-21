import type { Vec2 } from './geometry'

export function polyline(ctx: CanvasRenderingContext2D, pts: Vec2[]) {
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
  ctx.stroke()
}

export function polygon(ctx: CanvasRenderingContext2D, pts: Vec2[]) {
  ctx.beginPath()
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
  ctx.closePath()
  ctx.fill()
}

export function range(from: number, to: number, step: number) {
  const out: number[] = []
  for (let v = from; v <= to; v += step) out.push(v)
  return out
}

/** Etiqueta tipo "pastilla" centrada en (x, y). */
export function pill(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  opts: { font: string; color: string; swatch?: string },
) {
  ctx.font = opts.font
  const tw = ctx.measureText(text).width
  const sw = opts.swatch ? 10 : 0
  const w = tw + 14 + sw
  const h = 20
  // que no se salga por los bordes del canvas
  const left = Math.min(Math.max(4, x - w / 2), ctx.canvas.clientWidth - w - 4)
  ctx.fillStyle = 'rgba(10,14,20,.82)'
  ctx.beginPath()
  ctx.roundRect(left, y - h / 2, w, h, 5)
  ctx.fill()
  if (opts.swatch) {
    ctx.fillStyle = opts.swatch
    ctx.beginPath()
    ctx.arc(left + 9, y, 3.5, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.fillStyle = opts.color
  ctx.textBaseline = 'middle'
  ctx.fillText(text, left + 7 + sw, y + 1)
  ctx.textBaseline = 'alphabetic'
}
