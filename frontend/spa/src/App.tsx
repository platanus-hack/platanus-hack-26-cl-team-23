import { Link, Route, Routes } from 'react-router'
import { TrackMark } from './components/trazada/ui'
import Home from './pages/Home'
import NotFound from './pages/NotFound'
import { NAV_ACTIONS_ID } from './navActions'
import { ThemeToggle } from './components/ThemeToggle'

function App() {
  return (
    <div className="flex min-h-svh flex-col bg-bg text-fg">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-30 focus:rounded-ui focus:bg-fg focus:px-4 focus:py-2 focus:text-sm focus:text-bg"
      >
        Saltar al contenido
      </a>
      <header className="glass sticky top-0 z-20 border-b border-line">
        <nav className="mx-auto flex min-h-14 max-w-[1280px] items-center gap-x-6 px-4 py-2 sm:px-8">
          <Link to="/" className="flex min-h-11 items-center gap-2.5 rounded-ui focus-visible:outline-2 focus-visible:outline-offset-4">
            <TrackMark className="h-7 w-7" />
            <span className="text-xl font-semibold tracking-[-0.02em]">Trazada</span>
          </Link>
          <p className="hidden text-sm text-muted md:block">Metros extra en cada curva</p>
          {/* Cada página pone aquí su acción principal (con createPortal) */}
          <div id={NAV_ACTIONS_ID} className="ml-auto flex items-center gap-3" />
          <ThemeToggle />
        </nav>
      </header>

      <main id="contenido" className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-10 sm:px-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      <footer>
        <p className="label mx-auto flex max-w-[1280px] flex-wrap gap-x-6 gap-y-1 px-4 py-6 text-muted sm:px-8">
          <span>Trazada · metros extra por curva, medidos cuadro a cuadro</span>
          <span className="ml-auto">Platanus Hack 26 · Santiago</span>
        </p>
      </footer>
    </div>
  )
}

export default App
