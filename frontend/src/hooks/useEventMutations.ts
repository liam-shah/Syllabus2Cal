import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { EventUpdate } from '../types'
import { replaceCachedEvents, updateCachedEvents } from './eventCache'
import { queryKeys } from './queryKeys'

/** Save an edit from the edit form. Waits for the server, so validation errors can be shown. */
export function useUpdateEvent(uploadId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, changes }: { eventId: number; changes: EventUpdate }) =>
      api.updateEvent(eventId, changes),
    onSuccess: (saved) => replaceCachedEvents(queryClient, uploadId, [saved]),
  })
}

/**
 * Tick or untick an event. *Optimistic*: the checkbox changes immediately, before the server
 * replies, and is rolled back if the save fails.
 */
export function useSetIncluded(uploadId: number) {
  const queryClient = useQueryClient()
  const setIncludedInCache = (eventId: number, included: boolean) =>
    updateCachedEvents(queryClient, uploadId, (event) => (event.id === eventId ? { ...event, included } : event))

  return useMutation({
    mutationFn: ({ eventId, included }: { eventId: number; included: boolean }) =>
      api.updateEvent(eventId, { included }),

    onMutate: async ({ eventId, included }) => {
      // Stop an in-flight refetch from overwriting the optimistic change with older data.
      await queryClient.cancelQueries({ queryKey: queryKeys.events(uploadId) })
      setIncludedInCache(eventId, included)
    },

    // Undo only *this* event's change. Restoring a snapshot of the whole list instead would
    // also undo any other rows the user ticked while this request was in flight.
    onError: (_error, { eventId, included }) => setIncludedInCache(eventId, !included),

    onSuccess: (saved) => replaceCachedEvents(queryClient, uploadId, [saved]),
  })
}
