import { googleSignInUrl } from '../api/client'
import { useAuthStatus } from '../hooks/useAuthStatus'

/** Shows whether Google Calendar is connected, with a button to connect (or reconnect). */
export default function AuthStatusBanner() {
  const status = useAuthStatus()

  // The query result is a discriminated union: once loading and error are handled,
  // TypeScript knows status.data is defined.
  if (status.isPending) {
    return <p className="text-sm text-slate-500">Checking Google Calendar connection…</p>
  }

  if (status.isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Couldn't check the Google connection: {status.error.message}
      </p>
    )
  }

  if (status.data.connected) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="font-medium text-green-700">✓ Google Calendar connected</span>
        {/* Google's Testing mode expires access after 7 days, so reconnecting is a normal action. */}
        <a href={googleSignInUrl} className="text-slate-500 underline hover:text-slate-800">
          Reconnect
        </a>
      </div>
    )
  }

  return (
    <a
      href={googleSignInUrl}
      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
    >
      Connect Google Calendar
    </a>
  )
}
