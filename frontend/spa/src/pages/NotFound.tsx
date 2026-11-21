import { Link } from 'react-router'

export default function NotFound() {
  return (
    <section className="space-y-4 text-center">
      <p className="text-6xl font-bold text-emerald-400">404</p>
      <h1 className="text-2xl font-semibold text-white">Página no encontrada</h1>
      <Link
        to="/"
        className="inline-block rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400"
      >
        Ir al inicio
      </Link>
    </section>
  )
}
