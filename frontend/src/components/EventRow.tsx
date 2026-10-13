import { useState } from 'react'

import { formatDate, formatTimeRange } from '../format'
import { useSetIncluded, useUpdateEvent } from '../hooks/useEventMutations'
import type { EventUpdate, ExtractedEvent } from '../types'
import EventEditForm from './EventEditForm'

const EVENT_TABLE_COLUMNS = 6 // must match the headings in EventReviewTable

interface EventRowProps {
  event: ExtractedEvent
  /**
   * The upload whose cached event list this row belongs to. Passed down from the table (which
   * owns that cache) rather than read from event.upload_id, so there is only one source of truth
   * for which cache entry to update.
   */
  uploadId: number
}

/** One event in the review table: an include checkbox, the event, and an Edit button. */
export default function EventRow({ event, uploadId }: EventRowProps) {
  const [isEditing, setIsEditing] = useState(false)
  // Each row has its own mutations, so "saving" and errors belong to that row only.
  const setIncluded = useSetIncluded(uploadId)
  const update = useUpdateEvent(uploadId)

  const isLocked = event.status === 'synced'
  const lockedReason = 'Already in Google Calendar, so it can no longer be changed here.'

  function startEditing() {
    update.reset() // clear an error left over from a previous attempt
    setIsEditing(true)
  }

  function save(changes: EventUpdate) {
    if (Object.keys(changes).length === 0) {
      setIsEditing(false) // nothing changed, so there's nothing to send
      return
    }
    update.mutate({ eventId: event.id, changes }, { onSuccess: () => setIsEditing(false) })
  }

  if (isEditing) {
    return (
      <tr className="bg-blue-50/40">
        <td colSpan={EVENT_TABLE_COLUMNS} className="px-3 py-2">
          <EventEditForm
            event={event}
            isSaving={update.isPending}
            error={update.isError ? update.error.message : null}
            onSave={save}
            onCancel={() => setIsEditing(false)}
          />
        </td>
      </tr>
    )
  }

  const details = [event.location, event.description].filter(Boolean).join(' · ')
  const rowStyle = !event.included ? 'opacity-60' : event.date_is_approximate ? 'bg-amber-50/60' : undefined

  return (
    <tr className={rowStyle}>
      <td className="px-3 py-2 align-top">
        <input
          type="checkbox"
          aria-label={`Include ${event.title}`}
          checked={event.included}
          // Disabled while saving so two clicks can't race each other to the server.
          disabled={isLocked || setIncluded.isPending}
          title={isLocked ? lockedReason : undefined}
          onChange={(e) => setIncluded.mutate({ eventId: event.id, included: e.target.checked })}
          className="mt-1 size-4"
        />
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top">
        <div>{formatDate(event.start_date)}</div>
        <div className="text-xs text-slate-500">{formatTimeRange(event.start_time, event.end_time)}</div>
        {event.date_is_approximate && (
          <span
            title="The PDF only gives the week, not the exact day. Check it before syncing."
            className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800"
          >
            Approx. date
          </span>
        )}
      </td>
      <td className="px-3 py-2 align-top">
        <div className="font-medium">{event.title}</div>
        <StatusBadge event={event} />
        {setIncluded.isError && (
          <p role="alert" className="mt-1 text-xs text-red-700">
            Couldn't save that change: {setIncluded.error.message}
          </p>
        )}
      </td>
      <td className="whitespace-pre-line px-3 py-2 align-top text-slate-600">{details || '—'}</td>
      <td className="px-3 py-2 align-top">
        <code className="whitespace-pre-wrap text-xs text-slate-500">{event.source_snippet ?? '—'}</code>
      </td>
      <td className="px-3 py-2 align-top">
        <button
          type="button"
          onClick={startEditing}
          disabled={isLocked}
          title={isLocked ? lockedReason : undefined}
          aria-label={`Edit ${event.title}`}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Edit
        </button>
      </td>
    </tr>
  )
}

function StatusBadge({ event }: { event: ExtractedEvent }) {
  switch (event.status) {
    case 'pending_review':
      return null
    case 'edited':
      return <span className="text-xs text-blue-700">Edited</span>
    case 'synced':
      return <span className="text-xs text-green-700">✓ In Google Calendar</span>
    case 'sync_failed':
      return <span className="text-xs text-red-700" title={event.sync_error ?? undefined}>Sync failed</span>
    default: {
      // Only reachable if a new status is added to types.ts without a badge here - and then
      // this line stops compiling, because the leftover status isn't assignable to `never`.
      const unhandled: never = event.status
      return unhandled
    }
  }
}
