import { setTheme, useTheme } from '../trazada/theme'

/** Botón discreto del header: alterna claro / oscuro y recuerda la elección. */
export function ThemeToggle() {
  const theme = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const label = next === 'dark' ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro'
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={label}
      title={label}
      className="-mr-2 grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted transition-colors hover:bg-paper2 hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}

const MoonIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" />
  </svg>
)

const SunIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
  </svg>
)
