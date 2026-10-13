import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { queryKeys } from '../hooks/queryKeys'
import { ApiError } from './client'

const MAX_RETRIES = 2

/** Retrying only helps if the failure might be temporary: no connection, or a server error. */
function isWorthRetrying(error: Error): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500)
}

export function createQueryClient(): QueryClient {
  // 401 means the session ended (expired, or signed out in another tab). Wherever that's
  // noticed, re-check who is signed in, and the app switches to the sign-in screen. Handled
  // once here, on the caches, instead of in every query and mutation.
  const recheckSignInOn401 = (error: Error) => {
    if (error instanceof ApiError && error.status === 401) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.authStatus })
    }
  }

  const queryClient = new QueryClient({
    queryCache: new QueryCache({ onError: recheckSignInOn401 }),
    mutationCache: new MutationCache({ onError: recheckSignInOn401 }),
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
  return queryClient
}
