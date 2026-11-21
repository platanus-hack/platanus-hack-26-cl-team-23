import { useEffect, useRef, useState } from 'react'

const reduceMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/**
 * Hace "rodar" un número hasta su valor nuevo (salida exponencial, como un contador).
 * Con prefers-reduced-motion salta directo al valor.
 */
export function useTween(target: number, ms = 700): number {
  const [shown, setShown] = useState(target)
  const from = useRef(target)
  const shownRef = useRef(target)

  useEffect(() => {
    if (reduceMotion() || !Number.isFinite(target)) {
      shownRef.current = target
      const id = requestAnimationFrame(() => setShown(target))
      return () => cancelAnimationFrame(id)
    }
    from.current = shownRef.current
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(2, -10 * k) // easeOutExpo
      const v = from.current + (target - from.current) * (k === 1 ? 1 : eased)
      shownRef.current = v
      setShown(v)
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])

  return shown
}
