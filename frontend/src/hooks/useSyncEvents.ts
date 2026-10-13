import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import { replaceCachedEvents } from './eventCache'
import { queryKeys } from './queryKeys'

/** Send the upload's ticked events to Google Calendar. Never retried automatically (see queryClient.ts). */
export function useSyncEvents(uploadId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.syncEvents(uploadId),

    // The server returns every event it attempted, with its new status.
    onSuccess: (attempted) => replaceCachedEvents(queryClient, uploadId, attempted),

    // A sync can stop part-way (e.g. Google rejects the sign-in at event 12) after some events
    // were already saved as synced. The error response doesn't say which, so reload the list.
    onError: () => queryClient.invalidateQueries({ queryKey: queryKeys.events(uploadId) }),
  })
}
