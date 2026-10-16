import { act, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { POLL_INTERVAL_MS } from '../hooks/useUpload'
import { makeEvent, makeUpload } from '../test/factories'
import { jsonResponse, mockFetch } from '../test/mockFetch'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import UploadProgress from './UploadProgress'

afterEach(() => {
  vi.useRealTimers()
})

describe('UploadProgress', () => {
  it('keeps checking while Claude works, then shows the events', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let status: 'processing' | 'extracted' = 'processing'
    const fetchMock = mockFetch((url) =>
      url.includes('/events/preview') ? jsonResponse([makeEvent()]) : jsonResponse(makeUpload({ status })),
    )
    renderWithQueryClient(<UploadProgress uploadId={7} />)

    expect(await screen.findByText(/Extracting events from cpsc213.pdf/)).toBeInTheDocument()

    status = 'extracted' // the background job finishes
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS))

    expect(await screen.findByRole('heading', { name: 'Review extracted events' })).toBeInTheDocument()
    const uploadChecks = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/uploads/7'))
    expect(uploadChecks).toHaveLength(2)

    // Finished: no more polling.
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3))
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/uploads/7'))).toHaveLength(2)
  })

  it('says why extraction failed', async () => {
    mockFetch(() => jsonResponse(makeUpload({ status: 'failed', error_message: 'Claude API call failed' })))
    renderWithQueryClient(<UploadProgress uploadId={7} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't extract events from cpsc213.pdf: Claude API call failed",
    )
  })
})
