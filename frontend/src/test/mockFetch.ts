import { vi } from 'vitest'

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>

/** Replace the browser's fetch for one test. Returns the mock so tests can inspect calls. */
export function mockFetch(handler: Handler) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => Promise.resolve(handler(String(input), init)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
