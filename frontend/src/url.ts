// The parts of the app's state that live in the page URL. Pure functions over a query
// string (e.g. "?google=connected&upload=3"), so they're easy to test.

import { SIGN_IN_FAILURE_REASONS, type SignInFailureReason } from './types'

export type SignInResult =
  | { outcome: 'connected' } // signed in, with Google Calendar connected
  | { outcome: 'no_calendar' } // signed in, but not allowed to add calendar events yet
  | { outcome: 'failed'; reason: SignInFailureReason | 'unknown' }

function isSignInFailureReason(value: string | null): value is SignInFailureReason {
  return SIGN_IN_FAILURE_REASONS.some((reason) => reason === value)
}

/** What the backend's sign-in redirect reported: ?google=connected|no_calendar, or ?google=error&reason=... */
export function readSignInResult(search: string): SignInResult | null {
  const params = new URLSearchParams(search)
  const google = params.get('google')
  if (google === 'connected') return { outcome: 'connected' }
  if (google === 'no_calendar') return { outcome: 'no_calendar' }
  if (google === 'error') {
    const reason = params.get('reason')
    // Never trust a URL: an unrecognised code becomes 'unknown' rather than being shown.
    return { outcome: 'failed', reason: isSignInFailureReason(reason) ? reason : 'unknown' }
  }
  return null
}

/** The upload being reviewed (?upload=3), so refreshing the page doesn't lose it. */
export function readUploadId(search: string): number | null {
  const value = new URLSearchParams(search).get('upload')
  if (value === null) return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

/** The sign-in params are one-off messages: remove them so a refresh doesn't repeat them. */
export function withoutSignInParams(search: string): string {
  const params = new URLSearchParams(search)
  params.delete('google')
  params.delete('reason')
  return toSearch(params)
}

export function withUploadId(search: string, uploadId: number | null): string {
  const params = new URLSearchParams(search)
  if (uploadId === null) {
    params.delete('upload')
  } else {
    params.set('upload', String(uploadId))
  }
  return toSearch(params)
}

function toSearch(params: URLSearchParams): string {
  const query = params.toString()
  return query ? `?${query}` : ''
}
