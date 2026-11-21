import { Link, Route, Routes } from 'react-router'
import Home from './pages/Home'
import NotFound from './pages/NotFound'

function App() {
  return (
    <div className="min-h-svh bg-bg text-fg">
      <header className="border-b border-line">
        <nav className="mx-auto flex min-h-14 max-w-[1280px] flex-wrap items-center gap-x-6 gap-y-1 px-4 py-2 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5 font-display text-2xl leading-none font-extrabold tracking-wide">
            <Logo />
            TRAZADA
          </Link>
          <span className="text-sm text-muted">
            Metros extra en cada curva
          </span>
        </nav>
      </header>

      <main className="mx-auto max-w-[1280px] px-4 py-6 sm:px-8">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}

function Logo() {
  return (
    <svg viewBox="0 0 42 24" className="h-6 w-[42px]" aria-hidden="true">
      <path d="M2 22 L14 2 H22 L10 22 Z" fill="var(--color-accent)" />
      <path d="M18 22 L30 2 H38 L26 22 Z" fill="var(--color-accent)" />
    </svg>
  )
}

export default App
