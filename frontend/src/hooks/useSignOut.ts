import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { AuthStatus } from '../types'
import { queryKeys } from './queryKeys'

/** Sign out, then forget everything cached for this user. */
export function useSignOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.signOut(),
    onSuccess: () => {
      // First switch the app to signed out (which unmounts the event table)...
      queryClient.setQueryData<AuthStatus>(queryKeys.authStatus, { signed_in: false })
      // ...then drop this user's cached data, so whoever signs in next on this browser
      // can never be shown it, even for a moment.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== queryKeys.authStatus[0] })
    },
  })
}
