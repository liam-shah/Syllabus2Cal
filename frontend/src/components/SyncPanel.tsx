import { plural } from '../format'
import { useAuthStatus } from '../hooks/useAuthStatus'
import type { ExtractedEvent } from '../types'

interface SyncPanelProps {
  events: ExtractedEvent[]
  onSync: () => void
  isSyncing: boolean
  /** The events the last sync attempted, if it succeeded. */
  lastResult: ExtractedEvent[] | undefined
  error: string | null
}

/** The "Sync to Google Calendar" button, why it might be disabled, and what the last sync did. */
export default function SyncPanel({ events, onSync, isSyncing, lastResult, error }: SyncPanelProps) {
  const authStatus = useAuthStatus()
  const isConnected = authStatus.data?.signed_in === true && authStatus.data.calendar_connected

  // Same rule as the backend's ExtractedEvent.is_waiting_to_sync.
  const waiting = events.filter((event) => event.included && event.status !== 'synced')
  const approximateWaiting = waiting.filter((event) => event.date_is_approximate).length

  // Until the connection check answers, say so - rather than briefly telling a connected
  // user to "connect Google Calendar".
  const disabledReason = authStatus.isPending
    ? 'Checking the Google Calendar connection…'
    : !isConnected
      ? 'Connect Google Calendar (top right) to sync.'
      : waiting.length === 0
        ? 'Nothing to sync - tick the events you want in your calendar.'
        : null

  return (
    <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSync}
          disabled={disabledReason !== null || isSyncing}
          className="rounded-md bg-green-700 px-4 py-2 text-sm font-medium text-white hover:bg-green-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isSyncing ? 'Syncing…' : `Sync ${plural(waiting.length, 'event')} to Google Calendar`}
        </button>
        {disabledReason !== null && !isSyncing && <span className="text-sm text-slate-600">{disabledReason}</span>}
        {disabledReason === null && !isSyncing && approximateWaiting > 0 && (
          <span className="text-sm text-amber-800">
            {plural(approximateWaiting, 'of these has', 'of these have')} an approximate date.
          </span>
        )}
      </div>

      {/* aria-live: screen readers announce progress and results when they appear. */}
      <div aria-live="polite" className="mt-2 text-sm">
        {isSyncing && (
          <p className="text-slate-600">Adding events to Google Calendar one at a time. This can take about 30 seconds.</p>
        )}
        {!isSyncing && error !== null && (
          <p role="alert" className="text-red-700">{error}</p>
        )}
        {!isSyncing && error === null && lastResult !== undefined && <SyncSummary attempted={lastResult} />}
      </div>
    </div>
  )
}

function SyncSummary({ attempted }: { attempted: ExtractedEvent[] }) {
  const added = attempted.filter((event) => event.status === 'synced').length
  const failed = attempted.length - added
  return (
    <p role="status" className={failed > 0 ? 'text-amber-800' : 'text-green-800'}>
      {plural(added, 'event')} added to Google Calendar
      {failed > 0 && ` · ${failed} failed (see the rows marked "Sync failed", then sync again to retry them)`}
    </p>
  )
}
