import { Link } from 'react-router'

export default function NotFound() {
  return (
    <section className="space-y-4 text-center">
      <p className="text-6xl font-bold text-fg">404</p>
      <h1 className="text-2xl font-semibold text-fg">Página no encontrada</h1>
      <Link
        to="/"
        className="inline-flex min-h-11 items-center rounded-ui bg-accent px-5 text-sm font-semibold text-white transition-colors hover:bg-fg hover:text-bg"
      >
        Ir al inicio
      </Link>
    </section>
  )
}
