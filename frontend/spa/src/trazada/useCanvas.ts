import { useEffect, useRef, useState } from 'react'

/**
 * Canvas que se adapta al tamaño de su contenedor y a pantallas retina.
 * Devuelve el ref para el <canvas> y el tamaño en píxeles CSS.
 * El dibujo se hace en coordenadas CSS; aquí se escala por devicePixelRatio.
 */
export function useCanvas() {
  const ref = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      canvas.getContext('2d')?.setTransform(dpr, 0, 0, dpr, 0, 0)
      setSize({ w: width, h: height })
    })
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [])

  return { ref, size }
}
