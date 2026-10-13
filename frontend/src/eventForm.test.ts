import { describe, expect, it } from 'vitest'

import { buildEventUpdate, toFormValues } from './eventForm'
import { makeEvent } from './test/factories'

const EVENT = makeEvent({ title: 'Lab L1', start_date: '2026-09-21', start_time: '10:00', location: 'ICCS 005' })

describe('buildEventUpdate', () => {
  it('sends nothing when nothing changed', () => {
    expect(buildEventUpdate(EVENT, toFormValues(EVENT))).toEqual({})
  })

  it('sends only the fields that changed', () => {
    const values = { ...toFormValues(EVENT), startDate: '2026-09-23', title: 'Lab L1 (moved)' }
    expect(buildEventUpdate(EVENT, values)).toEqual({ start_date: '2026-09-23', title: 'Lab L1 (moved)' })
  })

  it('turns a cleared input into null, so the field is removed', () => {
    const values = { ...toFormValues(EVENT), startTime: '', location: '   ' }
    expect(buildEventUpdate(EVENT, values)).toEqual({ start_time: null, location: null })
  })

  it('ignores whitespace-only differences in the title', () => {
    expect(buildEventUpdate(EVENT, { ...toFormValues(EVENT), title: '  Lab L1  ' })).toEqual({})
  })
})
