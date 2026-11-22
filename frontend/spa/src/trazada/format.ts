// Números a la chilena: coma decimal.
export const fmtNum = (n: number, digits = 1) => n.toFixed(digits).replace('.', ',')

export const fmtSeconds = (n: number, digits = 1) => `${fmtNum(n, digits)} s`

/** Tiempo de carrera como se lee en una pista: 3:14,2 (minutos, segundos y décimas). */
export function fmtClock(seconds: number) {
  const total = Math.max(0, Math.round(seconds * 10) / 10)
  const m = Math.floor(total / 60)
  const s = total - m * 60
  return `${m}:${s.toFixed(1).padStart(4, '0').replace('.', ',')}`
}

/** Probabilidad como porcentaje entero; lo que no llega al 1 % se dice como tal. */
export const fmtPct = (p: number) => (p > 0 && p < 0.005 ? '<1 %' : `${Math.round(p * 100)} %`)

/** Lee un color del tema (index.css) para usarlo en canvas. */
export const themeColor = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim()

export const themeFont = (name: 'display' | 'sans' | 'mono') =>
  getComputedStyle(document.documentElement).getPropertyValue(`--font-${name}`).trim()
