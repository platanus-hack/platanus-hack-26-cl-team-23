import { useSyncExternalStore } from 'react'

// Tema claro u oscuro. Es solo un atributo en <html> (data-theme): index.css
// redefine los mismos tokens para "dark", así que ningún componente cambia.
//
// Quién manda, en orden:
//   1. ?tema=oscuro o ?tema=claro en la URL (para el escenario: se abre ya en oscuro)
//   2. lo que eligió la persona con el botón (localStorage)
//   3. lo que pide el sistema (prefers-color-scheme)
// La elección inicial la hace un script en index.html, antes de pintar, para
// que no parpadee en blanco. Aquí solo se lee y se cambia.

export type Theme = 'light' | 'dark'

const KEY = 'trazada-tema'

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#000000' : '#f5f5f7')
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* sin almacenamiento: vale solo para esta visita */
  }
}

function subscribe(onChange: () => void) {
  const mo = new MutationObserver(onChange)
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => mo.disconnect()
}

/**
 * El tema vigente. Los dibujos en canvas lo ponen en las dependencias de su
 * efecto: así vuelven a leer los colores y se redibujan cuando cambia.
 */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme, () => 'light')
}
