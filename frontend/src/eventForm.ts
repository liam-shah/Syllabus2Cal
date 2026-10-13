// The edit form's logic, kept out of the component so it's plain functions that are easy to test.

import type { EventUpdate, ExtractedEvent } from './types'

/** What the form's inputs hold. HTML inputs always give strings, so "" means "empty". */
export interface EventFormValues {
  title: string
  startDate: string // "YYYY-MM-DD" from <input type="date">
  dateIsApproximate: boolean
  startTime: string // "HH:MM" from <input type="time">, or ""
  endTime: string
  location: string
  description: string
}

export function toFormValues(event: ExtractedEvent): EventFormValues {
  return {
    title: event.title,
    startDate: event.start_date,
    dateIsApproximate: event.date_is_approximate,
    startTime: event.start_time ?? '',
    endTime: event.end_time ?? '',
    location: event.location ?? '',
    description: event.description ?? '',
  }
}

/**
 * Only the fields that actually changed, so the request says exactly what the user did -
 * and an unchanged field can never overwrite a newer value saved somewhere else.
 */
export function buildEventUpdate(event: ExtractedEvent, values: EventFormValues): EventUpdate {
  const update: EventUpdate = {}
  const title = values.title.trim()
  if (title !== event.title) update.title = title
  if (values.startDate !== event.start_date) update.start_date = values.startDate
  if (values.dateIsApproximate !== event.date_is_approximate) update.date_is_approximate = values.dateIsApproximate

  const startTime = emptyToNull(values.startTime)
  if (startTime !== event.start_time) update.start_time = startTime
  const endTime = emptyToNull(values.endTime)
  if (endTime !== event.end_time) update.end_time = endTime
  const location = emptyToNull(values.location.trim())
  if (location !== event.location) update.location = location
  const description = emptyToNull(values.description.trim())
  if (description !== event.description) update.description = description
  return update
}

function emptyToNull(value: string): string | null {
  return value === '' ? null : value
}
