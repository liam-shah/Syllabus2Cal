// Formatting helpers for showing API data on screen. Pure functions - easy to test.

import type { IsoDate } from './types'

/** "2026-09-15" -> "Tue, Sep 15, 2026": always the day written in the PDF. */
export function formatDate(isoDate: IsoDate): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  // Built from its parts on purpose. new Date("2026-09-15") means midnight *UTC*, which is
  // still Sep 14 in Vancouver - every date would show one day early.
  const date = new Date(year, month - 1, day)
  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
}

/** "14:00" + "15:30" -> "14:00–15:30"; no times -> "All day". */
export function formatTimeRange(startTime: string | null, endTime: string | null): string {
  if (startTime === null) return 'All day'
  return endTime === null ? startTime : `${startTime}–${endTime}`
}

/** plural(1, "event") -> "1 event"; plural(3, "event") -> "3 events". */
export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}
