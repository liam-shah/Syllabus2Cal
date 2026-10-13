import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { makeEvent } from '../test/factories'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import EventReviewTable from './EventReviewTable'

const LAB = makeEvent({
  id: 2,
  title: 'Lab L1: Numbers & Memory',
  start_date: '2026-09-21',
  date_is_approximate: true,
  location: 'ICCS 005',
})
const LECTURE = makeEvent({ id: 1, title: 'Lecture 1b: Pointers', start_date: '2026-10-01', start_time: '14:00' })

/** The table's body rows (the first row is the column headings). */
async function findEventRows() {
  const table = await screen.findByRole('table')
  return within(table).getAllByRole('row').slice(1)
}

describe('EventReviewTable', () => {
  it('requests the events for the given upload', async () => {
    const fetchMock = mockFetch(() => jsonResponse([LAB]))
    renderWithQueryClient(<EventReviewTable uploadId={7} />)

    await findEventRows()
    expect(fetchMock.mock.calls[0][0]).toBe('http://api.test/events/preview?upload_id=7')
  })

  it('shows every event with its date, time and details', async () => {
    mockFetch(() => jsonResponse([LAB, LECTURE]))
    renderWithQueryClient(<EventReviewTable uploadId={7} />)

    const [labRow, lectureRow] = await findEventRows()
    expect(labRow).toHaveTextContent('Mon, Sep 21, 2026')
    expect(labRow).toHaveTextContent('Lab L1: Numbers & Memory')
    expect(labRow).toHaveTextContent('ICCS 005')
    expect(labRow).toHaveTextContent('All day')
    expect(lectureRow).toHaveTextContent('Thu, Oct 1, 2026')
    expect(lectureRow).toHaveTextContent('14:00')
  })

  it('flags approximate dates, and only those', async () => {
    mockFetch(() => jsonResponse([LAB, LECTURE]))
    renderWithQueryClient(<EventReviewTable uploadId={7} />)

    const [labRow, lectureRow] = await findEventRows()
    expect(within(labRow).getByText('Approx. date')).toBeInTheDocument()
    expect(within(lectureRow).queryByText('Approx. date')).not.toBeInTheDocument()
    expect(screen.getByText(/2 events · 1 with approximate dates/)).toBeInTheDocument()
  })

  it('says so when the PDF had no events', async () => {
    mockFetch(() => jsonResponse([]))
    renderWithQueryClient(<EventReviewTable uploadId={7} />)

    expect(await screen.findByText('No events were found in this PDF.')).toBeInTheDocument()
  })

  it('shows the error when the upload does not exist', async () => {
    mockFetch(() => jsonResponse({ detail: 'Upload not found' }, 404))
    renderWithQueryClient(<EventReviewTable uploadId={999} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Upload not found')
  })
})
