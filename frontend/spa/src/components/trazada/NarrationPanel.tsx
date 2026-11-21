import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api'
import { generateNarration, type Narration } from '../../trazada/narration'
import type { Race } from '../../trazada/types'

type Props = {
  race: Race
  /** Reloj del video: la voz lo sigue cuadro a cuadro. */
  t: number
  playing: boolean
}

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; narration: Narration }
  | { kind: 'error'; message: string }

/** Un tramo por ventana de tiempo; el tramo activo es el último que ya empezó. */
function indexAt(narration: Narration, t: number): number | null {
  let found: number | null = null
  for (let i = 0; i < narration.segments.length; i++) {
    const segment = narration.segments[i]
    if (segment.start <= t) found = i
    if (segment.start > t) break
  }
  return found
}

/**
 * Relato del clip: Claude escribe el guion a partir de los hechos ya calculados y
 * ElevenLabs lo lee. La voz va enganchada al play del video: se pausa, se reanuda y
 * salta con la línea de tiempo.
 */
export function NarrationPanel({ race, t, playing }: Props) {
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [voice, setVoice] = useState(true)
  const audios = useRef<HTMLAudioElement[]>([])
  // El reloj del video cambia 60 veces por segundo; el efecto de audio solo debe reaccionar
  // al tramo y al play/pausa, así que la lectura de t pasa por un ref.
  const clock = useRef(t)
  useEffect(() => {
    clock.current = t
  }, [t])

  const narration = state.kind === 'ready' ? state.narration : undefined
  const active = narration ? indexAt(narration, t) : null

  // Un <audio> por tramo, listo para sonar en cuanto el video avance.
  useEffect(() => {
    audios.current.forEach((a) => a.pause())
    if (!narration) {
      audios.current = []
      return
    }
    audios.current = narration.audio.map((url) => {
      const element = new Audio(url)
      element.preload = 'auto'
      return element
    })
    return () => {
      audios.current.forEach((a) => a.pause())
      audios.current = []
    }
  }, [narration])

  useEffect(() => {
    audios.current.forEach((a) => a.pause())
    if (!narration || !voice || !playing || active === null) return
    const element = audios.current[active]
    const segment = narration.segments[active]
    if (!element) return

    // Si la voz del tramo es más larga que su ventana, se acelera un poco para no pisar
    // el tramo siguiente; es preferible a cortar una frase a la mitad.
    const window = Math.max(0.5, segment.end - segment.start)
    element.playbackRate = Math.min(1.35, Math.max(1, (segment.duration_s ?? window) / window))

    // El audio y el video avanzan a ritmos distintos si hay aceleración: se convierte.
    const offset = Math.max(0, (clock.current - segment.start) * element.playbackRate)
    if (Math.abs(element.currentTime - offset) > 0.25) element.currentTime = offset
    void element.play().catch(() => {})
  }, [narration, voice, playing, active])

  // Al desmontar (o cambiar de video, ver `key` en Home) se corta la voz.
  useEffect(() => () => audios.current.forEach((a) => a.pause()), [])

  async function generate() {
    setState({ kind: 'loading' })
    try {
      setState({ kind: 'ready', narration: await generateNarration(race) })
    } catch (e) {
      setState({
        kind: 'error',
        message: e instanceof ApiError ? e.message : 'No pudimos generar el relato.',
      })
    }
  }

  return (
    <section className="rounded-xl border border-line bg-panel px-5 py-4" aria-live="polite">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold">Relato</h2>
        {narration && (
          <p className="text-xs text-muted">
            {narration.source === 'llm' ? 'guion de Claude' : 'guion automático'} ·{' '}
            {narration.segments.length} tramos
            {narration.cached && ' · desde caché'}
            {narration.audio.length > 0 && voice && playing && ' · sonando'}
          </p>
        )}
        <div className="ml-auto flex items-center gap-3">
          {narration && narration.audio.length > 0 && (
            <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-muted select-none">
              <input
                type="checkbox"
                checked={voice}
                onChange={(e) => setVoice(e.target.checked)}
                className="accent-accent"
              />
              Voz
            </label>
          )}
          {state.kind === 'idle' && (
            <button
              type="button"
              onClick={generate}
              className="min-h-9 rounded-md bg-accent px-3 text-sm font-semibold text-bg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Generar relato
            </button>
          )}
          {state.kind === 'loading' && (
            <span className="font-mono text-xs text-muted">escribiendo el relato…</span>
          )}
          {narration && narration.audio.length === 0 && (
            <span className="text-xs text-muted">sin voz configurada, solo texto</span>
          )}
        </div>
      </header>

      {state.kind === 'error' && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-red-400/40 bg-red-400/10 px-3 py-2 text-sm text-red-200"
        >
          {state.message}
        </p>
      )}

      {narration && (
        <>
          <ol className="mt-3 flex flex-col gap-2">
            {narration.segments.map((segment, i) => (
              <li
                key={i}
                className={`flex gap-3 rounded-md px-2 py-1.5 transition-colors ${
                  active === i ? 'bg-pick/10' : ''
                }`}
              >
                <span className="w-12 shrink-0 pt-0.5 font-mono text-[11px] text-muted tabular-nums">
                  {segment.start.toFixed(0)}s
                </span>
                <p className={`text-sm ${active === i ? 'text-fg' : 'text-fg/80'}`}>{segment.text}</p>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted">{narration.disclaimer}</p>
        </>
      )}
    </section>
  )
}
