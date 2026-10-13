import { googleConnectCalendarUrl } from '../api/client'
import { useSignOut } from '../hooks/useSignOut'
import type { AuthStatus } from '../types'

type SignedIn = Extract<AuthStatus, { signed_in: true }>

interface AuthStatusBannerProps {
  account: SignedIn
}

/** Who is signed in, whether their Google Calendar is connected, and a way to sign out. */
export default function AuthStatusBanner({ account }: AuthStatusBannerProps) {
  const signOut = useSignOut()

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      {account.calendar_connected ? (
        <span className="flex items-center gap-2">
          <span className="font-medium text-green-700">✓ Google Calendar connected</span>
          {/* Google's Testing mode expires access after 7 days, so reconnecting is a normal action. */}
          <a href={googleConnectCalendarUrl} className="text-slate-500 underline hover:text-slate-800">
            Reconnect
          </a>
        </span>
      ) : (
        <a
          href={googleConnectCalendarUrl}
          className="rounded-md bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700"
        >
          Connect Google Calendar
        </a>
      )}

      <span className="text-slate-600">{account.email}</span>
      <button
        type="button"
        onClick={() => signOut.mutate()}
        disabled={signOut.isPending}
        className="text-slate-500 underline hover:text-slate-800 disabled:cursor-wait"
      >
        {signOut.isPending ? 'Signing out…' : 'Sign out'}
      </button>
      {signOut.isError && (
        <span role="alert" className="text-red-700">
          Couldn't sign out: {signOut.error.message}
        </span>
      )}
    </div>
  )
}
