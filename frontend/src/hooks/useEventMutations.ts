import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { EventUpdate, ExtractedEvent } from '../types'
import { queryKeys } from './queryKeys'

/**
 * Swap one event in the cached list, leaving the rest untouched. Cheaper than refetching
 * all ~60 events after every edit, and the server's response is the up-to-date copy anyway.
 */
function replaceCachedEvent(
  queryClient: QueryClient,
  uploadId: number,
  eventId: number,
  update: (event: ExtractedEvent) => ExtractedEvent,
) {
  queryClient.setQueryData<ExtractedEvent[]>(queryKeys.events(uploadId), (events) =>
    events?.map((event) => (event.id === eventId ? update(event) : event)),
  )
}

/** Save an edit from the edit form. Waits for the server, so validation errors can be shown. */
export function useUpdateEvent(uploadId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, changes }: { eventId: number; changes: EventUpdate }) =>
      api.updateEvent(eventId, changes),
    onSuccess: (saved) => replaceCachedEvent(queryClient, uploadId, saved.id, () => saved),
  })
}

/**
 * Tick or untick an event. *Optimistic*: the checkbox changes immediately, before the server
 * replies, and is rolled back if the save fails.
 */
export function useSetIncluded(uploadId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, included }: { eventId: number; included: boolean }) =>
      api.updateEvent(eventId, { included }),

    onMutate: async ({ eventId, included }) => {
      // Stop an in-flight refetch from overwriting the optimistic change with older data.
      await queryClient.cancelQueries({ queryKey: queryKeys.events(uploadId) })
      replaceCachedEvent(queryClient, uploadId, eventId, (event) => ({ ...event, included }))
    },

    onError: (_error, { eventId, included }) => {
      // Undo only *this* event's change. Restoring a snapshot of the whole list instead would
      // also undo any other rows the user ticked while this request was in flight.
      replaceCachedEvent(queryClient, uploadId, eventId, (event) => ({ ...event, included: !included }))
    },

    onSuccess: (saved) => replaceCachedEvent(queryClient, uploadId, saved.id, () => saved),
  })
}
