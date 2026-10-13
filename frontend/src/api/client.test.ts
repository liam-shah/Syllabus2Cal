import { describe, expect, it } from 'vitest'

import { jsonResponse, mockFetch } from '../test/mockFetch'
import { ApiError, api, googleSignInUrl } from './client'

describe('api client', () => {
  it('calls the configured backend URL and returns the parsed JSON', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ connected: true }))

    await expect(api.getAuthStatus()).resolves.toEqual({ connected: true })
    expect(fetchMock.mock.calls[0][0]).toBe('http://api.test/auth/google/status')
  })

  it("turns an error response into an ApiError carrying the backend's message", async () => {
    mockFetch(() => jsonResponse({ detail: 'Upload not found' }, 404))

    const error = await api.getEvents(999).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: 'Upload not found' })
  })

  it('falls back to a generic message when the error response is not JSON', async () => {
    mockFetch(() => new Response('<html>Bad Gateway</html>', { status: 502 }))

    await expect(api.getAuthStatus()).rejects.toMatchObject({ status: 502, message: 'Request failed (502)' })
  })

  it('explains when the backend cannot be reached', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch') // what fetch throws when nothing is listening
    })

    await expect(api.getAuthStatus()).rejects.toMatchObject({ status: 0, message: expect.stringContaining('reach the server') })
  })

  it('passes a cancelled request through as an abort, not as a server error', async () => {
    mockFetch(() => {
      throw new DOMException('The operation was aborted.', 'AbortError')
    })

    await expect(api.getAuthStatus()).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('uploads the file as multipart form data and lets the browser set Content-Type', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ id: 7 }, 201))
    const file = new File(['%PDF-1.7'], 'cpsc213.pdf', { type: 'application/pdf' })

    await api.uploadPdf(file)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://api.test/uploads')
    expect(init?.method).toBe('POST')
    const body = init?.body
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('file')).toBeInstanceOf(File)
    expect(init?.headers).toBeUndefined() // a hand-written Content-Type would break the upload
  })

  it('puts the upload id in the events query string', async () => {
    const fetchMock = mockFetch(() => jsonResponse([]))

    await api.getEvents(3)

    expect(fetchMock.mock.calls[0][0]).toBe('http://api.test/events/preview?upload_id=3')
  })

  it('points the sign-in link at the backend login route', () => {
    expect(googleSignInUrl).toBe('http://api.test/auth/google/login')
  })
})
