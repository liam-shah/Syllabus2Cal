import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { queryKeys } from './queryKeys'

/** How often to ask whether Claude has finished. Extraction takes about a minute. */
export const POLL_INTERVAL_MS = 2000

/**
 * One upload, re-fetched every few seconds while it's still processing (the backend extracts
 * events in the background). Polling stops by itself once the status is final.
 */
export function useUpload(uploadId: number) {
  return useQuery({
    queryKey: queryKeys.upload(uploadId),
    queryFn: ({ signal }) => api.getUpload(uploadId, signal),
    refetchInterval: (query) => (query.state.data?.status === 'processing' ? POLL_INTERVAL_MS : false),
  })
}
