import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Id del espacio de la barra superior donde cada página pone su acción principal. */
export const NAV_ACTIONS_ID = 'nav-actions'

/** Renderiza `children` en la barra superior (a la derecha). */
export function NavActions({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<HTMLElement | null>(null)
  // El espacio existe en el DOM recién después del primer render de App.
  useEffect(() => {
    const id = requestAnimationFrame(() => setTarget(document.getElementById(NAV_ACTIONS_ID)))
    return () => cancelAnimationFrame(id)
  }, [])
  return target ? createPortal(children, target) : null
}
