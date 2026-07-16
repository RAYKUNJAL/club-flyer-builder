let token: string | null = localStorage.getItem('sbi_token')

export function setToken(t: string | null) {
  token = t
  if (t) localStorage.setItem('sbi_token', t)
  else localStorage.removeItem('sbi_token')
}

export function getToken() {
  return token
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request(path: string, options: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = { ...(options.headers as any) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, { ...options, headers })
  if (res.status === 204) return null
  const ct = res.headers.get('content-type') ?? ''
  const data = ct.includes('json') ? await res.json() : await res.text()
  if (!res.ok) throw new ApiError(res.status, (data as any)?.detail ?? data)
  return data
}

export const api = {
  get: (path: string) => request(path),
  post: (path: string, body?: unknown) =>
    request(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  upload: (path: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(path, { method: 'POST', body: fd })
  },
}

export function labToCss(lab: number[] | null | undefined): string {
  if (!lab) return '#888'
  // Display-only approximation via the browser's lab() support fallback.
  return `lab(${lab[0]}% ${lab[1]} ${lab[2]})`
}

export function rgbToCss(rgb: number[] | null | undefined): string {
  if (!rgb) return '#888'
  return `rgb(${Math.round(rgb[0])}, ${Math.round(rgb[1])}, ${Math.round(rgb[2])})`
}

export function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === 'string') return e.detail
    return JSON.stringify(e.detail)
  }
  return String(e)
}
