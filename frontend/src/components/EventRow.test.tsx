import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { makeEvent } from '../test/factories'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import type { ExtractedEvent } from '../types'
import EventReviewTable from './EventReviewTable'

const LAB = makeEvent({
  id: 2,
  title: 'Lab L1',
  start_date: '2026-09-21',
  date_is_approximate: true,
  included: false,
  start_time: '10:00',
})

/**
 * Renders the real table (rows read their data from its cache) with a fake backend:
 * GET returns `events`, PATCH is answered by `onPatch`.
 */
function renderTable(events: ExtractedEvent[], onPatch: (body: Record<string, unknown>) => Response | Promise<Response>) {
  const fetchMock = mockFetch((_url, init) =>
    init?.method === 'PATCH' ? onPatch(JSON.parse(String(init.body))) : jsonResponse(events),
  )
  // Deliberately not 1 (the factory's upload_id): rows must update the cache the *table* owns,
  // not one worked out from the event data. When both were 1, a bug hid behind the coincidence.
  renderWithQueryClient(<EventReviewTable uploadId={42} />)
  return fetchMock
}

const patchCalls = (fetchMock: ReturnType<typeof mockFetch>) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')

describe('the include checkbox', () => {
  it('ticks before the server has replied, then saves in the background', async () => {
    const user = userEvent.setup()
    let respond!: (response: Response) => void
    const fetchMock = renderTable([LAB], () => new Promise<Response>((resolve) => { respond = resolve }))

    const checkbox = await screen.findByRole('checkbox', { name: 'Include Lab L1' })
    await user.click(checkbox)

    // The request is still unanswered here, so a tick can only come from the optimistic update.
    await waitFor(() => expect(checkbox).toBeChecked())
    await waitFor(() => expect(patchCalls(fetchMock)).toHaveLength(1))
    const [url, init] = patchCalls(fetchMock)[0]
    expect(url).toBe('http://api.test/events/2')
    expect(JSON.parse(String(init?.body))).toEqual({ included: true })

    respond(jsonResponse({ ...LAB, included: true }))
    await waitFor(() => expect(checkbox).toBeEnabled())
    expect(checkbox).toBeChecked()
  })

  it('rolls back and explains when the save fails', async () => {
    const user = userEvent.setup()
    renderTable([LAB], () => jsonResponse({ detail: 'Event not found' }, 404))

    const checkbox = await screen.findByRole('checkbox', { name: 'Include Lab L1' })
    await user.click(checkbox)

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save that change: Event not found")
    expect(checkbox).not.toBeChecked()
  })

  it('stays disabled while a save is in flight, so two clicks cannot race', async () => {
    const user = userEvent.setup()
    let respond!: (response: Response) => void
    renderTable([LAB], () => new Promise<Response>((resolve) => { respond = resolve }))

    const checkbox = await screen.findByRole('checkbox', { name: 'Include Lab L1' })
    await user.click(checkbox)
    expect(checkbox).toBeDisabled()

    respond(jsonResponse({ ...LAB, included: true }))
    await waitFor(() => expect(checkbox).toBeEnabled())
  })
})

describe('editing an event', () => {
  it('sends only what changed, then shows the saved event', async () => {
    const user = userEvent.setup()
    const saved = { ...LAB, start_date: '2026-09-23', date_is_approximate: false, status: 'edited' as const }
    const fetchMock = renderTable([LAB], () => jsonResponse(saved))

    await user.click(await screen.findByRole('button', { name: 'Edit Lab L1' }))
    const form = screen.getByRole('form', { name: 'Edit Lab L1' })
    const dateInput = within(form).getByLabelText('Date')
    await user.clear(dateInput)
    await user.type(dateInput, '2026-09-23')

    // Choosing a date unticks "approximate" in the form too - the same rule as the backend.
    expect(within(form).getByLabelText('Date is approximate')).not.toBeChecked()
    await user.click(within(form).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.queryByRole('form')).not.toBeInTheDocument())
    expect(JSON.parse(String(patchCalls(fetchMock)[0][1]?.body))).toEqual({
      start_date: '2026-09-23',
      date_is_approximate: false,
    })
    expect(screen.getByText('Wed, Sep 23, 2026')).toBeInTheDocument()
    expect(screen.getByText('Edited')).toBeInTheDocument()
    expect(screen.queryByText('Approx. date')).not.toBeInTheDocument()
  })

  it("keeps the form open and shows the server's reason when a save is rejected", async () => {
    const user = userEvent.setup()
    renderTable([LAB], () => jsonResponse({ detail: "The end time can't be before the start time." }, 400))

    await user.click(await screen.findByRole('button', { name: 'Edit Lab L1' }))
    const form = screen.getByRole('form', { name: 'Edit Lab L1' })
    await user.type(within(form).getByLabelText('End time'), '09:00')
    await user.click(within(form).getByRole('button', { name: 'Save' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent("can't be before the start time")
    expect(form).toBeInTheDocument()
  })

  it('closes without a request when nothing changed', async () => {
    const user = userEvent.setup()
    const fetchMock = renderTable([LAB], () => jsonResponse(LAB))

    await user.click(await screen.findByRole('button', { name: 'Edit Lab L1' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    expect(patchCalls(fetchMock)).toHaveLength(0)
  })

  it('throws away unsaved changes on Cancel', async () => {
    const user = userEvent.setup()
    renderTable([LAB], () => jsonResponse(LAB))

    await user.click(await screen.findByRole('button', { name: 'Edit Lab L1' }))
    const titleInput = screen.getByLabelText('Title')
    await user.clear(titleInput)
    await user.type(titleInput, 'Something else')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByText('Lab L1')).toBeInTheDocument()
    expect(screen.queryByText('Something else')).not.toBeInTheDocument()
  })
})

describe('a synced event', () => {
  it('is locked', async () => {
    renderTable([{ ...LAB, status: 'synced', included: true }], () => jsonResponse(LAB))

    expect(await screen.findByRole('checkbox', { name: 'Include Lab L1' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Edit Lab L1' })).toBeDisabled()
    expect(screen.getByText('✓ In Google Calendar')).toBeInTheDocument()
  })
})
