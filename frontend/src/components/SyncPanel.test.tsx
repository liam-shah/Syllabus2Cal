import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { makeEvent } from '../test/factories'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import type { ExtractedEvent } from '../types'
import EventReviewTable from './EventReviewTable'

const LECTURE = makeEvent({ id: 1, title: 'Lecture', start_date: '2026-09-15' })
const LAB = makeEvent({ id: 2, title: 'Lab', start_date: '2026-09-21', date_is_approximate: true, included: true })
const UNTICKED = makeEvent({ id: 3, title: 'Unticked quiz', start_date: '2026-09-22', included: false })
const ALREADY_SYNCED = makeEvent({ id: 4, title: 'Old lecture', start_date: '2026-09-08', status: 'synced' })

const synced = (event: ExtractedEvent): ExtractedEvent => ({ ...event, status: 'synced', google_event_id: `g${event.id}` })

interface FakeBackend {
  connected?: boolean
  events?: ExtractedEvent[]
  /** Answers POST /events/sync. */
  onSync?: () => Response | Promise<Response>
}

/** The real table, with a fake backend that answers auth status, the event list, and sync. */
function renderTable({ connected = true, events = [LECTURE, LAB, UNTICKED, ALREADY_SYNCED], onSync }: FakeBackend) {
  const fetchMock = mockFetch((url) => {
    if (url.endsWith('/auth/status')) return jsonResponse({ signed_in: true, email: 'a@example.com', calendar_connected: connected })
    if (url.includes('/events/sync')) return onSync!()
    return jsonResponse(events)
  })
  renderWithQueryClient(<EventReviewTable uploadId={7} />)
  return fetchMock
}

const syncButton = () => screen.findByRole('button', { name: /^Sync|Syncing/ })

describe('the sync button', () => {
  it('counts only ticked events that are not in the calendar yet', async () => {
    renderTable({})
    // Lecture and Lab: the unticked quiz and the already-synced lecture don't count.
    const button = await screen.findByRole('button', { name: 'Sync 2 events to Google Calendar' })
    await waitFor(() => expect(button).toBeEnabled()) // once the connection check has answered
  })

  it('says it is checking the connection instead of asking a connected user to connect', async () => {
    renderTable({})
    expect(await screen.findByText('Checking the Google Calendar connection…')).toBeInTheDocument()
    expect(screen.queryByText(/Connect Google Calendar \(top right\)/)).not.toBeInTheDocument()
  })

  it('warns when some of them have approximate dates', async () => {
    renderTable({})
    expect(await screen.findByText('1 of these has an approximate date.')).toBeInTheDocument()
  })

  it('is disabled, with the reason, until Google Calendar is connected', async () => {
    renderTable({ connected: false })
    expect(await screen.findByText(/Connect Google Calendar \(top right\)/)).toBeInTheDocument()
    expect(await syncButton()).toBeDisabled()
  })

  it('is disabled when there is nothing to sync', async () => {
    renderTable({ events: [UNTICKED, ALREADY_SYNCED] })
    expect(await screen.findByText(/Nothing to sync/)).toBeInTheDocument()
    expect(await syncButton()).toBeDisabled()
  })
})

describe('syncing', () => {
  it('locks the table while it runs, then shows what was added', async () => {
    const user = userEvent.setup()
    let respond!: (response: Response) => void
    const fetchMock = renderTable({ onSync: () => new Promise<Response>((resolve) => { respond = resolve }) })

    await user.click(await screen.findByRole('button', { name: 'Sync 2 events to Google Calendar' }))

    expect(await screen.findByRole('button', { name: 'Syncing…' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Include Lecture' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Edit Lecture' })).toBeDisabled()
    const syncCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/events/sync'))
    expect(syncCall?.[0]).toBe('http://api.test/events/sync?upload_id=7')
    expect(syncCall?.[1]?.method).toBe('POST')

    respond(jsonResponse([synced(LECTURE), synced(LAB)]))

    expect(await screen.findByRole('status')).toHaveTextContent('2 events added to Google Calendar')
    expect(screen.getAllByText('✓ In Google Calendar')).toHaveLength(3) // the two new ones + the old one
    expect(screen.getByRole('checkbox', { name: 'Include Lecture' })).toBeDisabled() // synced = locked
    expect(screen.getByText(/Nothing to sync/)).toBeInTheDocument()
  })

  it('reports events that failed, so they can be retried', async () => {
    const user = userEvent.setup()
    const failedLab = { ...LAB, status: 'sync_failed' as const, sync_error: 'Google Calendar rejected this event (400: Bad Request)' }
    renderTable({ onSync: () => jsonResponse([synced(LECTURE), failedLab]) })

    await user.click(await screen.findByRole('button', { name: 'Sync 2 events to Google Calendar' }))

    expect(await screen.findByRole('status')).toHaveTextContent('1 event added to Google Calendar · 1 failed')
    expect(screen.getByText('Sync failed')).toHaveAttribute('title', failedLab.sync_error)
    // The failed one is still waiting, so the button offers to retry it.
    expect(screen.getByRole('button', { name: 'Sync 1 event to Google Calendar' })).toBeEnabled()
  })

  it('shows the error and reloads the events when the sync stops part-way', async () => {
    const user = userEvent.setup()
    const fetchMock = renderTable({
      onSync: () => jsonResponse({ detail: 'Google rejected the saved sign-in - reconnect Google Calendar and sync again' }, 502),
    })
    await user.click(await screen.findByRole('button', { name: 'Sync 2 events to Google Calendar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('reconnect Google Calendar')
    const eventListLoads = () => fetchMock.mock.calls.filter(([url]) => String(url).includes('/events/preview')).length
    await waitFor(() => expect(eventListLoads()).toBe(2)) // loaded once at the start, once after the failure
  })
})
