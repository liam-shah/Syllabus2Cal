import type { ReactNode } from 'react'

import { plural } from '../format'
import { useEvents } from '../hooks/useEvents'
import EventRow from './EventRow'

interface EventReviewTableProps {
  uploadId: number
}

/** The review step: every extracted event, so the user can check them before syncing. */
export default function EventReviewTable({ uploadId }: EventReviewTableProps) {
  const events = useEvents(uploadId)

  if (events.isPending) {
    return (
      <ReviewSection>
        <p className="mt-3 text-sm text-slate-500">Loading events…</p>
      </ReviewSection>
    )
  }

  if (events.isError) {
    return (
      <ReviewSection>
        <p role="alert" className="mt-3 text-sm text-red-700">
          Couldn't load the events: {events.error.message}
        </p>
      </ReviewSection>
    )
  }

  if (events.data.length === 0) {
    return (
      <ReviewSection>
        <p className="mt-3 text-sm text-slate-600">No events were found in this PDF.</p>
      </ReviewSection>
    )
  }

  const approximateCount = events.data.filter((event) => event.date_is_approximate).length

  return (
    <ReviewSection>
      <p className="mt-1 text-sm text-slate-600">
        {plural(events.data.length, 'event')}
        {approximateCount > 0 && ` · ${approximateCount} with approximate dates (check these before syncing)`}
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <caption className="sr-only">Events extracted from the uploaded PDF</caption>
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-600">
            <tr>
              <th scope="col" className="px-3 py-2">Date</th>
              <th scope="col" className="px-3 py-2">Event</th>
              <th scope="col" className="px-3 py-2">Details</th>
              <th scope="col" className="px-3 py-2">Source text</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {/* key: a stable id lets React keep each row's identity across re-renders. */}
            {events.data.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </tbody>
        </table>
      </div>
    </ReviewSection>
  )
}

/** The card + heading every state shares. `children` is whatever is placed between the tags. */
function ReviewSection({ children }: { children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">Review extracted events</h2>
      {children}
    </section>
  )
}
