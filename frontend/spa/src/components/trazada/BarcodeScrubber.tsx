import { useMemo } from 'react'
import { fmtNum } from '../../trazada/format'
import type { Race } from '../../trazada/types'

type Props = {
  race: Race
  t: number
  onSeek: (t: number) => void
}

const BARS = 140

/**
 * Línea de tiempo dibujada como un código de barras: cada barra es un instante de la carrera
 * y su altura es cuántos corredores ve el detector en ese momento (sale de /tracking/track).
 * Los cambios de plano de la cámara (de /zones) se marcan con un punto arriba.
 * Lo corrido va en tinta, lo que viene en gris, el instante actual en naranja.
 * Debajo hay un <input type="range"> invisible: teclado, arrastre y lectores de pantalla gratis.
 */
export function BarcodeScrubber({ race, t, onSeek }: Props) {
  const duration = race.video.duration

  const { values, cuts } = useMemo(() => {
    const counts: number[] = []
    for (let i = 0; i < BARS; i++) {
      const ti = ((i + 0.5) / BARS) * duration
      // cuadro más cercano a ti (los cuadros están ordenados por t)
      let lo = 0
      let hi = race.frames.length - 1
      while (lo < hi) {
        const mid = (lo + hi) >> 1
        if (race.frames[mid].t < ti) lo = mid + 1
        else hi = mid
      }
      counts.push(race.frames[lo]?.runners.length ?? 0)
    }
    const max = Math.max(...counts, 1)
    const cutBars = new Set((race.camera?.cuts ?? []).map((s) => Math.min(BARS - 1, Math.floor((s / duration) * BARS))))
    return { values: counts.map((v) => v / max), cuts: cutBars }
  }, [race, duration])

  const nowIdx = Math.min(BARS - 1, Math.floor((t / duration) * BARS))

  return (
    <div className="relative h-11 min-w-40 flex-1 rounded-md has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-4 has-[input:focus-visible]:outline-[var(--color-accent)]">
      <svg viewBox={`0 0 ${BARS * 4} 44`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden="true">
        {values.map((v, i) => {
          const h = 6 + v * 30
          const isNow = i === nowIdx
          return (
            // Altura fija y escala en Y (transform): animar transform es barato; animar height no.
            <rect
              key={i}
              x={i * 4 + 0.5}
              y={4}
              width={isNow ? 2.5 : 1.6}
              height={40}
              rx={0.8}
              fill={isNow ? 'var(--color-pick)' : i < nowIdx ? 'var(--color-fg)' : 'var(--color-other)'}
              opacity={isNow ? 1 : i < nowIdx ? 0.85 : 0.45}
              style={{
                transform: `scaleY(${isNow ? 1 : h / 40})`,
                transformOrigin: 'center bottom',
                transformBox: 'fill-box',
                transition: 'transform 300ms var(--ease-out)',
              }}
            />
          )
        })}
        {[...cuts].map((i) => (
          <circle key={`c${i}`} cx={i * 4 + 1.3} cy={2} r={1.6} fill="var(--color-muted)" />
        ))}
      </svg>
      <input
        type="range"
        min={0}
        max={duration}
        step={0.01}
        value={t}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Línea de tiempo"
        aria-valuetext={`${fmtNum(t, 1)} de ${fmtNum(duration, 1)} segundos`}
        className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
      />
    </div>
  )
}
