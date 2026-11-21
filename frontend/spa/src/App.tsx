import { Link, NavLink, Route, Routes } from 'react-router'
import About from './pages/About'
import Home from './pages/Home'
import NotFound from './pages/NotFound'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-emerald-500 text-slate-950'
      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
  }`

function App() {
  return (
    <div className="min-h-svh bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <nav className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-3">
          <Link to="/" className="mr-auto font-semibold tracking-tight">
            spa
          </Link>
          <NavLink to="/" end className={navLinkClass}>
            Inicio
          </NavLink>
          <NavLink to="/about" className={navLinkClass}>
            Acerca
          </NavLink>
        </nav>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-10">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
