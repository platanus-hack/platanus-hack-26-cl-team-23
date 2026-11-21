import { useHealth } from '../hooks/useHealth'
import type { HealthResponse } from '../types/api'

export default function Home() {
  const { data, isPending, isError, error, refetch } = useHealth()

  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-bold tracking-tight text-white">
        React + Vite + TypeScript
      </h1>
      <p className="text-slate-300">
        Proyecto configurado con <strong>Tailwind CSS 4</strong>,{' '}
        <strong>React Router 8</strong>, <strong>Zustand</strong> y{' '}
        <strong>TanStack Query</strong>.
      </p>

      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Estado de la API
        </p>
        <ApiStatus
          health={data}
          isPending={isPending}
          isError={isError}
          error={error}
          onRetry={() => void refetch()}
        />
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <p className="text-sm text-slate-400">
          Edita{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-emerald-400">
            src/pages/Home.tsx
          </code>{' '}
          y guarda para probar el HMR.
        </p>
      </div>
    </section>
  )
}

type ApiStatusProps = {
  health: HealthResponse | undefined
  isPending: boolean
  isError: boolean
  error: Error | null
  onRetry: () => void
}

function ApiStatus({ health, isPending, isError, error, onRetry }: ApiStatusProps) {
  if (isPending) {
    return (
      <p className="flex items-center gap-2 text-sm text-amber-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
        Conectando con la API…
      </p>
    )
  }

  if (isError || !health) {
    return (
      <div className="space-y-2">
        <p className="flex items-center gap-2 text-sm text-red-400">
          <span className="h-2 w-2 rounded-full bg-red-400" />
          API no disponible{error ? ` (${error.message})` : ''}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700"
        >
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <p className="flex items-center gap-2 text-sm text-emerald-400">
      <span className="h-2 w-2 rounded-full bg-emerald-400" />
      API conectada · env <code className="text-emerald-300">{health.env}</code> · v
      {health.version}
    </p>
  )
}
