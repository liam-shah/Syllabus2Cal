import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderWithQueryClient } from '../test/renderWithQueryClient'
import AuthStatusBanner from './AuthStatusBanner'

const CONNECT_URL = 'http://api.test/auth/google/login?connect_calendar=true'

describe('AuthStatusBanner', () => {
  it('shows who is signed in, with a way to sign out', () => {
    renderWithQueryClient(<AuthStatusBanner account={{ signed_in: true, email: 'a@example.com', calendar_connected: true }} />)

    expect(screen.getByText('a@example.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeEnabled()
  })

  it('offers to connect when Google Calendar is not connected', () => {
    renderWithQueryClient(<AuthStatusBanner account={{ signed_in: true, email: 'a@example.com', calendar_connected: false }} />)

    // Connecting asks Google for the permissions screen again (connect_calendar=true).
    expect(screen.getByRole('link', { name: 'Connect Google Calendar' })).toHaveAttribute('href', CONNECT_URL)
  })

  it('shows the connection, with a way to reconnect', () => {
    renderWithQueryClient(<AuthStatusBanner account={{ signed_in: true, email: 'a@example.com', calendar_connected: true }} />)

    expect(screen.getByText(/Google Calendar connected/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Reconnect' })).toHaveAttribute('href', CONNECT_URL)
  })
})
