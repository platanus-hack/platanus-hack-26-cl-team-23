// Piezas del sistema de diseño de TRAZADA. Toda la pantalla se arma con estas.
// Su aspecto sale 100% de los tokens de index.css.

import type { ButtonHTMLAttributes, ReactNode } from 'react'

/**
 * Sección: cabecera con título (y un dato de contexto a la derecha) + cuerpo.
 * `flush` deja el cuerpo sin margen interno (para video y mapas, que llegan al borde).
 */
export function Figure({
  title,
  meta,
  flush = false,
  children,
  className = '',
  bodyClassName = '',
}: {
  title: string
  meta?: ReactNode
  flush?: boolean
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`fig ${className}`}>
      <header className="fig-head">
        <h2 className="title">{title}</h2>
        {meta && <span className="label ml-auto text-muted">{meta}</span>}
      </header>
      <div className={`${flush ? 'fig-body--flush' : 'fig-body'} ${bodyClassName}`}>{children}</div>
    </section>
  )
}

/**
 * Título de página: dice QUÉ se midió y CUÁNTOS metros; debajo, una fila de datos
 * técnicos en mono (como una ficha), separados por espacio, sin adornos.
 */
export function PageTitle({ title, lede, facts }: { title: ReactNode; lede?: ReactNode; facts?: string[] }) {
  return (
    <div className="min-w-0">
      <h1 className="h1 max-w-[18ch] break-words">{title}</h1>
      {lede && <p className="mt-4 max-w-[52ch] text-xl leading-snug text-muted">{lede}</p>}
      {facts && facts.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1">
          {facts.map((f) => (
            <li key={f} className="label text-muted">
              {f}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'quiet' }

export function Button({ variant = 'quiet', className = '', ...rest }: ButtonProps) {
  const look = variant === 'primary' ? 'bg-accent text-white hover:bg-fg hover:text-bg' : 'bg-paper2 text-fg hover:bg-line'
  return (
    <button
      type="button"
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-ui px-5 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 ${look} ${className}`}
      {...rest}
    />
  )
}

/** Lo que aún falta: un campo plano y un texto que explica qué va a aparecer ahí. */
export function Pending({ children }: { children: ReactNode }) {
  return <p className="rounded-inner bg-paper2 p-4 text-sm leading-relaxed text-muted">{children}</p>
}

/**
 * Marca de TRAZADA: una T hecha de carriles. Monocroma; toma el color del texto
 * (currentColor), así que en fondo oscuro pasa a blanco sola.
 */
export function TrackMark({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      className={className}
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeWidth="3.6"
    >
      <path d="M4 6 H36" />
      <path d="M4 13 H8 A6 6 0 0 1 14 19 V36" />
      <path d="M36 13 H32 A6 6 0 0 0 26 19 V36" />
      <path d="M20 13 V36" />
    </svg>
  )
}
