import { describe, expect, it } from 'vitest'

import { formatDate, formatTimeRange, plural } from './format'

describe('formatDate', () => {
  it('shows the day written in the PDF, even west of UTC', () => {
    // The trap this guards against: tests run in Vancouver time (vite.config.ts), where
    // new Date("2026-09-15") is still the evening of Sep 14.
    expect(new Date('2026-09-15').getDate()).toBe(14)
    expect(formatDate('2026-09-15')).toBe('Tue, Sep 15, 2026')
  })
})

describe('formatTimeRange', () => {
  it.each([
    [null, null, 'All day'],
    ['14:00', null, '14:00'],
    ['14:00', '15:30', '14:00–15:30'],
  ])('start %s, end %s -> %s', (start, end, expected) => {
    expect(formatTimeRange(start, end)).toBe(expected)
  })
})

describe('plural', () => {
  it('only adds an s when the count is not 1', () => {
    expect(plural(1, 'event')).toBe('1 event')
    expect(plural(0, 'event')).toBe('0 events')
    expect(plural(59, 'event')).toBe('59 events')
  })

  it('accepts an irregular plural', () => {
    expect(plural(1, 'of these has', 'of these have')).toBe('1 of these has')
    expect(plural(3, 'of these has', 'of these have')).toBe('3 of these have')
  })
})
