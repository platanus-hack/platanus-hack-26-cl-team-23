import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Reloj de la reproducción. Entrega el tiempo actual (s) y controles.
 * Es el "reproductor" que avanza un cuadro a la vez: los dibujos solo
 * miran el cuadro vigente y los anteriores, igual que en vivo.
 */
export function usePlayback(duration: number) {
  const reduceMotion =
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [t, setT] = useState(reduceMotion ? duration * 0.75 : 0)
  const [playing, setPlaying] = useState(!reduceMotion)
  const last = useRef<number | null>(null)

  useEffect(() => {
    if (!playing || duration <= 0) return
    let raf = 0
    const tick = (now: number) => {
      if (last.current !== null) {
        const dt = (now - last.current) / 1000
        setT((prev) => (prev + dt >= duration ? 0 : prev + dt))
      }
      last.current = now
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      last.current = null
    }
  }, [playing, duration])

  const seek = useCallback(
    (next: number) => {
      setPlaying(false)
      setT(Math.min(duration, Math.max(0, next)))
    },
    [duration],
  )

  return { t, playing, toggle: () => setPlaying((p) => !p), seek }
}
