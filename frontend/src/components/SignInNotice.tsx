import type { SignInFailureReason } from '../types'
import type { SignInResult } from '../url'

// A Record over the union means TypeScript errors if a new reason is added without a message.
const FAILURE_MESSAGES: Record<SignInFailureReason | 'unknown', string> = {
  access_denied: 'Google sign-in was cancelled.',
  google_error: 'Google reported a problem during sign-in. Please try again.',
  invalid_state: 'That sign-in link expired or was already used. Please try again.',
  exchange_failed: "Google didn't accept the sign-in. Please try again.",
  unknown: 'Google sign-in failed. Please try again.',
}

interface SignInNoticeProps {
  result: SignInResult | null
}

/** The one-off message shown after coming back from Google's sign-in page. */
export default function SignInNotice({ result }: SignInNoticeProps) {
  if (result === null) return null

  if (result.outcome === 'connected') {
    return (
      <p role="status" className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
        Signed in, with Google Calendar connected. You can now upload a schedule.
      </p>
    )
  }

  if (result.outcome === 'no_calendar') {
    return (
      <p role="status" className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        Signed in, but Syllabus2Cal isn't allowed to add events to your calendar yet. You can still upload and
        review a schedule; use Connect Google Calendar (top right) when you're ready to sync.
      </p>
    )
  }

  return (
    <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      {FAILURE_MESSAGES[result.reason]}
    </p>
  )
}
