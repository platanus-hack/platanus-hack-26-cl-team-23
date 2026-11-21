import { Link } from 'react-router'

export default function About() {
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-bold tracking-tight text-white">Acerca</h1>
      <p className="text-slate-300">
        Ruta de ejemplo en <code className="rounded bg-slate-800 px-1.5 py-0.5 text-emerald-400">/about</code>.
      </p>
      <Link
        to="/"
        className="inline-block rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400"
      >
        Volver al inicio
      </Link>
    </section>
  )
}
