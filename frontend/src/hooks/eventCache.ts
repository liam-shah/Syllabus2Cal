import type { QueryClient } from '@tanstack/react-query'

import type { ExtractedEvent } from '../types'
import { queryKeys } from './queryKeys'

/**
 * Change the cached copies of some events, leaving the rest of the list untouched. Cheaper than
 * refetching all ~60 events after every change.
 */
export function updateCachedEvents(
  queryClient: QueryClient,
  uploadId: number,
  update: (event: ExtractedEvent) => ExtractedEvent,
) {
  queryClient.setQueryData<ExtractedEvent[]>(queryKeys.events(uploadId), (events) => events?.map(update))
}

/** Replace cached events with the server's up-to-date copies (matched by id). */
export function replaceCachedEvents(queryClient: QueryClient, uploadId: number, saved: ExtractedEvent[]) {
  const savedById = new Map(saved.map((event) => [event.id, event]))
  updateCachedEvents(queryClient, uploadId, (event) => savedById.get(event.id) ?? event)
}
