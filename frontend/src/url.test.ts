import { describe, expect, it } from 'vitest'

import { readSignInResult, readUploadId, withUploadId, withoutSignInParams } from './url'

describe('readSignInResult', () => {
  it('reads a successful sign-in', () => {
    expect(readSignInResult('?google=connected')).toEqual({ outcome: 'connected' })
    expect(readSignInResult('?google=no_calendar')).toEqual({ outcome: 'no_calendar' })
  })

  it('reads a known failure reason', () => {
    expect(readSignInResult('?google=error&reason=access_denied')).toEqual({ outcome: 'failed', reason: 'access_denied' })
  })

  it('treats an unrecognised reason as unknown instead of trusting the URL', () => {
    expect(readSignInResult('?google=error&reason=<script>')).toEqual({ outcome: 'failed', reason: 'unknown' })
    expect(readSignInResult('?google=error')).toEqual({ outcome: 'failed', reason: 'unknown' })
  })

  it('returns null when the page was not opened from a sign-in', () => {
    expect(readSignInResult('')).toBeNull()
    expect(readSignInResult('?upload=3')).toBeNull()
  })
})

describe('readUploadId', () => {
  it('reads a positive whole number', () => {
    expect(readUploadId('?upload=3')).toBe(3)
  })

  it.each(['', '?upload=', '?upload=abc', '?upload=0', '?upload=-2', '?upload=1.5'])('ignores %s', (search) => {
    expect(readUploadId(search)).toBeNull()
  })
})

describe('URL updates', () => {
  it('removes the one-off sign-in params but keeps everything else', () => {
    expect(withoutSignInParams('?google=error&reason=access_denied&upload=3')).toBe('?upload=3')
    expect(withoutSignInParams('?google=connected')).toBe('')
  })

  it('sets and removes the upload id', () => {
    expect(withUploadId('', 3)).toBe('?upload=3')
    expect(withUploadId('?upload=3', 4)).toBe('?upload=4')
    expect(withUploadId('?upload=3', null)).toBe('')
  })
})
