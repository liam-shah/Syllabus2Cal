import { describe, expect, it } from 'vitest'

import { ApiError } from './client'
import { createQueryClient } from './queryClient'

const { queries, mutations } = createQueryClient().getDefaultOptions()
const shouldRetry = queries?.retry as (failureCount: number, error: Error) => boolean

describe('retry policy', () => {
  it('retries failures that might be temporary, at most twice', () => {
    expect(shouldRetry(0, new ApiError(0, 'no connection'))).toBe(true)
    expect(shouldRetry(1, new ApiError(503, 'server error'))).toBe(true)
    expect(shouldRetry(2, new ApiError(503, 'server error'))).toBe(false)
  })

  it('never retries a failure that will happen the same way again', () => {
    expect(shouldRetry(0, new ApiError(404, 'Upload not found'))).toBe(false)
    expect(shouldRetry(0, new ApiError(400, 'not a PDF'))).toBe(false)
  })

  it('never retries uploads or other changes automatically', () => {
    expect(mutations?.retry).toBe(false)
  })
})
