// Types for the data the backend sends. They mirror backend/app/schemas.py and
// backend/app/domain.py, and are kept in sync by hand for now.
//
// Statuses are string unions rather than TypeScript enums: the compiler setting
// `erasableSyntaxOnly` doesn't allow enums, and unions are the more common style anyway.
// They do the same job as the backend's StrEnums - 'synched' is a compile-time error.

/** A date as the API sends it: "YYYY-MM-DD", with no time or timezone. */
export type IsoDate = string

export type UploadStatus = 'extracted' | 'failed'

export type EventStatus = 'pending_review' | 'edited' | 'synced' | 'sync_failed'

/**
 * Why Google sign-in failed (backend/app/routers/auth.py: SignInFailure).
 * A runtime array as well as a type, because codes arriving in the URL have to be checked
 * at runtime; the type is derived from the array so the two can never drift apart.
 */
export const SIGN_IN_FAILURE_REASONS = ['access_denied', 'google_error', 'invalid_state', 'exchange_failed'] as const
export type SignInFailureReason = (typeof SIGN_IN_FAILURE_REASONS)[number]

export interface Upload {
  id: number
  filename: string
  status: UploadStatus
  error_message: string | null
  created_at: string
}

export interface ExtractedEvent {
  id: number
  upload_id: number
  title: string
  start_date: IsoDate
  date_is_approximate: boolean
  start_time: string | null // "HH:MM", 24-hour
  end_time: string | null
  location: string | null
  description: string | null
  source_snippet: string | null
  included: boolean
  status: EventStatus
  google_event_id: string | null
  sync_error: string | null
}

export interface AuthStatus {
  connected: boolean
}
