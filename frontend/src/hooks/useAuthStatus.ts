import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { queryKeys } from './queryKeys'

/** Whether Google Calendar is connected. */
export function useAuthStatus() {
  return useQuery({
    queryKey: queryKeys.authStatus,
    // TanStack passes an AbortSignal so it can cancel the request if it's no longer needed.
    queryFn: ({ signal }) => api.getAuthStatus(signal),
  })
}
