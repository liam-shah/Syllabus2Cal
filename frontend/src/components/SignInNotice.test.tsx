import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import SignInNotice from './SignInNotice'

describe('SignInNotice', () => {
  it('confirms a successful sign-in', () => {
    render(<SignInNotice result={{ outcome: 'connected' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Google Calendar connected')
  })

  it.each([
    ['access_denied', 'cancelled'],
    ['google_error', 'Google reported a problem'],
    ['invalid_state', 'expired or was already used'],
    ['exchange_failed', "didn't accept the sign-in"],
    ['unknown', 'sign-in failed'],
  ] as const)('explains the %s failure in plain words', (reason, expectedText) => {
    render(<SignInNotice result={{ outcome: 'failed', reason }} />)
    expect(screen.getByRole('alert')).toHaveTextContent(expectedText)
  })

  it('shows nothing when the page was not opened from a sign-in', () => {
    const { container } = render(<SignInNotice result={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
