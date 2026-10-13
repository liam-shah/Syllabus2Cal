import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import App from './App'
import { createQueryClient } from './api/queryClient'
import { jsonResponse, mockFetch } from './test/mockFetch'
import type { AuthStatus } from './types'

const SIGNED_IN: AuthStatus = { signed_in: true, email: 'a@example.com', calendar_connected: true }

/** The whole app, with the real query client (including its sign-in handling). */
function renderApp() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <App />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('App', () => {
  it('asks signed-out visitors to sign in, and shows nothing else', async () => {
    mockFetch(() => jsonResponse({ signed_in: false }))
    renderApp()

    expect(await screen.findByRole('link', { name: 'Sign in with Google' })).toHaveAttribute(
      'href',
      'http://api.test/auth/google/login',
    )
    expect(screen.queryByRole('heading', { name: 'Upload a schedule' })).not.toBeInTheDocument()
  })

  it('shows the app once signed in', async () => {
    mockFetch(() => jsonResponse(SIGNED_IN))
    renderApp()

    expect(await screen.findByText('a@example.com')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Upload a schedule' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Sign in with Google' })).not.toBeInTheDocument()
  })

  it('returns to the sign-in screen after signing out', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch((url) => {
      if (url.endsWith('/auth/sign-out')) return new Response(null, { status: 204 })
      return jsonResponse(SIGNED_IN)
    })
    renderApp()

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('link', { name: 'Sign in with Google' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith('/auth/sign-out') && init?.method === 'POST')).toBe(true)
  })

  it('goes back to the sign-in screen when the session has ended', async () => {
    // e.g. signed out in another tab: the server stops recognising this browser.
    window.history.replaceState(null, '', '/?upload=7')
    let sessionEnded = false
    mockFetch((url) => {
      if (url.endsWith('/auth/status')) return jsonResponse(sessionEnded ? { signed_in: false } : SIGNED_IN)
      sessionEnded = true
      return jsonResponse({ detail: "You're not signed in. Sign in with Google to continue." }, 401)
    })
    renderApp()

    expect(await screen.findByRole('link', { name: 'Sign in with Google' })).toBeInTheDocument()
  })
})
