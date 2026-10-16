import { describe, expect, it } from 'vitest'

import { jsonResponse, mockFetch } from '../test/mockFetch'
import { ApiError, api, googleConnectCalendarUrl, googleSignInUrl } from './client'

describe('api client', () => {
  it('calls the configured backend URL and returns the parsed JSON', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ signed_in: false }))

    await expect(api.getAuthStatus()).resolves.toEqual({ signed_in: false })
    expect(fetchMock.mock.calls[0][0]).toBe('http://api.test/auth/status')
  })

  it('sends the session cookie with every request', async () => {
    // The backend is on another origin, where fetch leaves cookies off unless told otherwise.
    const fetchMock = mockFetch(() => jsonResponse([]))

    await api.getEvents(3)
    await api.updateEvent(5, { included: false })

    expect(fetchMock.mock.calls.map(([, init]) => init?.credentials)).toEqual(['include', 'include'])
  })

  it('signs out with a POST, which answers with no content', async () => {
    const fetchMock = mockFetch(() => new Response(null, { status: 204 }))

    await expect(api.signOut()).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][0]).toBe('http://api.test/auth/sign-out')
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
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

  it('sends an edit as a JSON PATCH to that event', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ id: 5 }))

    await api.updateEvent(5, { included: false })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://api.test/events/5')
    expect(init?.method).toBe('PATCH')
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(init?.body).toBe('{"included":false}')
  })

  it("turns FastAPI's validation errors into readable sentences", async () => {
    mockFetch(() =>
      jsonResponse(
        {
          detail: [
            { loc: ['body', 'start_time'], msg: 'Value error, use 24-hour time like 14:00' },
            { loc: ['body'], msg: "Value error, title can't be empty" },
          ],
        },
        422,
      ),
    )

    await expect(api.updateEvent(5, {})).rejects.toMatchObject({
      status: 422,
      message: "Start time: use 24-hour time like 14:00. Title can't be empty.",
    })
  })

  it("starts a sync with a POST for that upload, in the browser's time zone", async () => {
    const fetchMock = mockFetch(() => jsonResponse([]))

    await api.syncEvents(7)

    const [url, init] = fetchMock.mock.calls[0]
    // Tests run with TZ=America/Vancouver (vite.config.ts), so that's the browser's zone here.
    expect(url).toBe('http://api.test/events/sync?upload_id=7&time_zone=America%2FVancouver')
    expect(init?.method).toBe('POST')
  })

  it('points the sign-in links at the backend login route', () => {
    expect(googleSignInUrl).toBe('http://api.test/auth/google/login')
    expect(googleConnectCalendarUrl).toBe('http://api.test/auth/google/login?connect_calendar=true')
  })
})
