import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { queryKeys } from './queryKeys'

/** The extracted events for one upload, sorted by date (the backend sorts them). */
export function useEvents(uploadId: number) {
  return useQuery({
    queryKey: queryKeys.events(uploadId),
    queryFn: ({ signal }) => api.getEvents(uploadId, signal),
  })
}
