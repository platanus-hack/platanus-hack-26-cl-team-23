const API_BASE = '/api'

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { headers, ...rest } = init ?? {}

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      Accept: 'application/json',
      ...headers,
    },
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status} en ${path}`)
  }

  return response.json() as Promise<T>
}
