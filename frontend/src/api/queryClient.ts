import { QueryClient } from '@tanstack/react-query'

import { ApiError } from './client'

const MAX_RETRIES = 2

/** Retrying only helps if the failure might be temporary: no connection, or a server error. */
function isWorthRetrying(error: Error): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500)
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A 404 or 400 will fail the same way every time, so don't retry those.
        retry: (failureCount, error) => failureCount < MAX_RETRIES && isWorthRetrying(error),
      },
      mutations: {
        // Never retry changes automatically: an upload costs a Claude call and a minute of
        // waiting, and a silent retry could create a duplicate upload.
        retry: false,
      },
    },
  })
}
