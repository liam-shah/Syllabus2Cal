import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, mockFetch } from '../test/mockFetch'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import AuthStatusBanner from './AuthStatusBanner'

describe('AuthStatusBanner', () => {
  it('offers to connect when Google Calendar is not connected', async () => {
    mockFetch(() => jsonResponse({ connected: false }))
    renderWithQueryClient(<AuthStatusBanner />)

    const link = await screen.findByRole('link', { name: 'Connect Google Calendar' })
    expect(link).toHaveAttribute('href', 'http://api.test/auth/google/login')
  })

  it('shows the connection, with a way to reconnect', async () => {
    mockFetch(() => jsonResponse({ connected: true }))
    renderWithQueryClient(<AuthStatusBanner />)

    expect(await screen.findByText(/Google Calendar connected/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Reconnect' })).toHaveAttribute('href', 'http://api.test/auth/google/login')
  })

  it('explains when the status check fails', async () => {
    mockFetch(() => {
      throw new TypeError('Failed to fetch')
    })
    renderWithQueryClient(<AuthStatusBanner />)

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't reach the server")
  })
})
