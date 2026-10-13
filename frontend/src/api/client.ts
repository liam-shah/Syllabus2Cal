// The only module that talks to the backend over HTTP. Components and hooks call these
// functions; nothing else in the frontend uses fetch directly.

import { config } from '../config'
import type { AuthStatus, ExtractedEvent, Upload } from '../types'

/** Any failed request. `message` is safe to show to the user. */
export class ApiError extends Error {
  readonly status: number // HTTP status, or 0 if the server couldn't be reached

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${config.apiUrl}${path}`, init)
  } catch (error) {
    // Cancelled on purpose (e.g. the component unmounted): let the caller see the abort.
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, "Couldn't reach the server. Is the backend running?")
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response))
  }
  // Trusts our own backend's response shape; the types mirror backend/app/schemas.py.
  return (await response.json()) as T
}

/** The backend reports errors as {"detail": "..."}; fall back to a generic message. */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Not JSON (e.g. a proxy error page) - use the fallback below.
  }
  return `Request failed (${response.status})`
}

export const api = {
  getAuthStatus(signal?: AbortSignal): Promise<AuthStatus> {
    return request<AuthStatus>('/auth/google/status', { signal })
  },

  uploadPdf(file: File): Promise<Upload> {
    const form = new FormData()
    form.append('file', file)
    // No Content-Type header: the browser must set it itself, including the multipart boundary.
    return request<Upload>('/uploads', { method: 'POST', body: form })
  },

  getEvents(uploadId: number, signal?: AbortSignal): Promise<ExtractedEvent[]> {
    const query = new URLSearchParams({ upload_id: String(uploadId) })
    return request<ExtractedEvent[]>(`/events/preview?${query}`, { signal })
  },
}

/** Sign-in is a page navigation (the browser leaves the app), not a fetch - so just a URL. */
export const googleSignInUrl = `${config.apiUrl}/auth/google/login`
