import { formatDate, formatTimeRange } from '../format'
import type { ExtractedEvent } from '../types'

interface EventRowProps {
  event: ExtractedEvent
}

/** One event in the review table. Read-only for now; editing comes in slice 2. */
export default function EventRow({ event }: EventRowProps) {
  const details = [event.location, event.description].filter(Boolean).join(' · ')

  return (
    <tr className={event.date_is_approximate ? 'bg-amber-50/60' : undefined}>
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
      <td className="px-3 py-2 align-top font-medium">{event.title}</td>
      <td className="whitespace-pre-line px-3 py-2 align-top text-slate-600">{details || '—'}</td>
      <td className="px-3 py-2 align-top">
        <code className="whitespace-pre-wrap text-xs text-slate-500">{event.source_snippet ?? '—'}</code>
      </td>
    </tr>
  )
}
