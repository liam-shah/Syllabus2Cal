// The only module that talks to the backend over HTTP. Components and hooks call these
// functions; nothing else in the frontend uses fetch directly.

import { config } from '../config'
import type { AuthStatus, EventUpdate, ExtractedEvent, Upload } from '../types'

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
    // credentials: 'include' sends the session cookie along. The backend runs on another
    // origin (port 8000), and fetch leaves cookies off cross-origin requests unless asked.
    response = await fetch(`${config.apiUrl}${path}`, { ...init, credentials: 'include' })
  } catch (error) {
    // Cancelled on purpose (e.g. the component unmounted): let the caller see the abort.
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, "Couldn't reach the server. Is the backend running?")
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response))
  }
  if (response.status === 204) return undefined as T // "No Content": nothing to parse
  // Trusts our own backend's response shape; the types mirror backend/app/schemas.py.
  return (await response.json()) as T
}

/**
 * The backend reports errors as {"detail": "..."}, except request validation errors (422),
 * where FastAPI sends {"detail": [{"loc": ["body", "start_time"], "msg": "..."}, ...]}.
 */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      if (typeof body.detail === 'string') return body.detail
      if (Array.isArray(body.detail)) {
        const messages = body.detail.map(formatValidationError).filter((message) => message !== null)
        if (messages.length > 0) return messages.join(' ')
      }
    }
  } catch {
    // Not JSON (e.g. a proxy error page) - use the fallback below.
  }
  return `Request failed (${response.status})`
}

/** {"loc": ["body", "start_time"], "msg": "Value error, use 24-hour time"} -> "Start time: use 24-hour time." */
function formatValidationError(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('msg' in error) || typeof error.msg !== 'string') return null
  const message = withFullStop(error.msg.replace(/^Value error, /, ''))
  const field = 'loc' in error && Array.isArray(error.loc) ? error.loc.at(-1) : undefined
  if (typeof field !== 'string' || field === 'body') return capitalise(message) // a rule about the whole request
  return `${capitalise(field.replaceAll('_', ' '))}: ${message}`
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function withFullStop(text: string): string {
  return /[.!?]$/.test(text) ? text : `${text}.`
}

export const api = {
  getAuthStatus(signal?: AbortSignal): Promise<AuthStatus> {
    return request<AuthStatus>('/auth/status', { signal })
  },

  signOut(): Promise<void> {
    return request<void>('/auth/sign-out', { method: 'POST' })
  },

  uploadPdf(file: File): Promise<Upload> {
    const form = new FormData()
    form.append('file', file)
    // No Content-Type header: the browser must set it itself, including the multipart boundary.
    return request<Upload>('/uploads', { method: 'POST', body: form })
  },

  getUpload(uploadId: number, signal?: AbortSignal): Promise<Upload> {
    return request<Upload>(`/uploads/${uploadId}`, { signal })
  },

  getEvents(uploadId: number, signal?: AbortSignal): Promise<ExtractedEvent[]> {
    const query = new URLSearchParams({ upload_id: String(uploadId) })
    return request<ExtractedEvent[]>(`/events/preview?${query}`, { signal })
  },

  updateEvent(eventId: number, changes: EventUpdate): Promise<ExtractedEvent> {
    return request<ExtractedEvent>(`/events/${eventId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    })
  },

  /** Sync the upload's ticked events; returns the events it attempted, with their new status. */
  syncEvents(uploadId: number): Promise<ExtractedEvent[]> {
    const query = new URLSearchParams({
      upload_id: String(uploadId),
      // The browser's IANA zone (e.g. "America/Toronto"): a PDF's "14:00" lands at 14:00 local time.
      time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    })
    return request<ExtractedEvent[]>(`/events/sync?${query}`, { method: 'POST' })
  },
}

// Signing in is a page navigation (the browser leaves the app for Google), not a fetch - so
// these are just URLs for links.
export const googleSignInUrl = `${config.apiUrl}/auth/google/login`
/** Same sign-in, but Google shows the permissions screen again: the way to (re)connect the calendar. */
export const googleConnectCalendarUrl = `${googleSignInUrl}?connect_calendar=true`
