// Números a la chilena: coma decimal.
export const fmtNum = (n: number, digits = 1) => n.toFixed(digits).replace('.', ',')

export const fmtMeters = (n: number, digits = 1) => `${n >= 0 ? '+' : '−'}${fmtNum(Math.abs(n), digits)} m`

export const fmtSeconds = (n: number, digits = 1) => `${fmtNum(n, digits)} s`

/** Lee un color del tema (index.css) para usarlo en canvas. */
export const themeColor = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim()

export const themeFont = (name: 'display' | 'sans' | 'mono') =>
  getComputedStyle(document.documentElement).getPropertyValue(`--font-${name}`).trim()
