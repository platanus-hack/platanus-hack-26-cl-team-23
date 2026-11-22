import { useRef, useState } from 'react'
import type { Race } from '../../trazada/types'
import { TopView } from './TopView'

type Props = {
  race: Race
  frameIndex: number
  selectedId?: number
  title: string
}

/**
 * La vista cenital con un botón de zoom: abre la misma pista en un modal que ocupa casi toda
 * la pantalla. Sigue el mismo cuadro del video, así que se mueve en vivo con el play.
 */
export function TopViewZoom({ race, frameIndex, selectedId, title }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  // El modal solo dibuja mientras está abierto: no hay dos lienzos repintando por cada cuadro.
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <TopView race={race} frameIndex={frameIndex} selectedId={selectedId} />
      <button
        type="button"
        onClick={() => {
          setOpen(true)
          dialog.current?.showModal()
        }}
        aria-label="Ampliar la pista"
        className="glass absolute top-3 right-3 grid h-11 w-11 place-items-center rounded-full text-fg transition-transform hover:scale-105 focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <ExpandIcon />
      </button>

      {/* Sin `display` propio en el <dialog>: pisaría el display:none de cuando está cerrado. */}
      <dialog
        ref={dialog}
        onClose={() => setOpen(false)}
        // clic sobre el fondo oscuro (el propio <dialog>, no su contenido) → cerrar
        onClick={(e) => e.target === e.currentTarget && dialog.current?.close()}
        aria-label={title}
        className="m-auto h-[92svh] w-[96vw] max-h-none max-w-[1700px] overflow-hidden rounded-section bg-surface p-0 text-fg backdrop:bg-black/60"
      >
        <div className="flex h-full flex-col">
          <header className="flex shrink-0 items-center gap-4 border-b border-line px-6 py-3">
            <h2 className="title">{title}</h2>
            <span className="label text-muted">Pista de 400 m · carriles ensanchados</span>
            <button
              type="button"
              onClick={() => dialog.current?.close()}
              className="ml-auto inline-flex min-h-11 items-center rounded-ui bg-paper2 px-5 text-sm font-semibold transition-colors hover:bg-line focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Cerrar
            </button>
          </header>
          <div className="min-h-0 flex-1">
            {open && <TopView race={race} frameIndex={frameIndex} selectedId={selectedId} fill />}
          </div>
        </div>
      </dialog>
    </div>
  )
}

const ExpandIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M9.5 2H14v4.5M6.5 14H2V9.5M14 2 9 7M2 14l5-5" />
  </svg>
)
