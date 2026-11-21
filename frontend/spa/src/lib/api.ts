// Cliente HTTP del backend. Mismo origen: en desarrollo Vite proxya /api a :8080 y
// en Vercel el rewrite de vercel.json manda /api/* al orchestrator.

const API_BASE = '/api'

/** Error con el sobre que devuelve el backend: {detail, error_code}. */
export class ApiError extends Error {
  status: number
  code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }

  /** 502/503/429: tiene sentido reintentar. 4xx del cliente, no. */
  get retryable() {
    return this.status === 429 || this.status >= 500
  }
}

async function readError(response: Response, path: string): Promise<ApiError> {
  try {
    const body = (await response.json()) as { detail?: unknown; error_code?: string }
    // DomainError manda un string; los 422 de FastAPI, una lista de ValidationError.
    const detail =
      typeof body.detail === 'string'
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
          : undefined
    if (detail) return new ApiError(response.status, detail, body.error_code)
  } catch {
    // respuesta sin JSON (proxy caído, HTML de error…)
  }
  return new ApiError(response.status, `HTTP ${response.status} en ${path}`)
}

type Options = Omit<RequestInit, 'body'> & { body?: BodyInit | null }

async function request<T>(path: string, init?: Options): Promise<T> {
  const { headers, ...rest } = init ?? {}

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      Accept: 'application/json',
      ...headers,
    },
  })

  if (!response.ok) throw await readError(response, path)

  return response.json() as Promise<T>
}

export function apiFetch<T>(path: string, init?: Options): Promise<T> {
  return request<T>(path, init)
}

/** POST con cuerpo JSON. */
export function apiPost<T>(path: string, body: unknown, init?: Options): Promise<T> {
  return request<T>(path, {
    ...init,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    body: JSON.stringify(body),
  })
}

/** POST multipart. Sin Content-Type: lo pone el navegador con su boundary. */
export function apiUpload<T>(path: string, form: FormData, init?: Options): Promise<T> {
  return request<T>(path, { ...init, method: 'POST', body: form })
}
