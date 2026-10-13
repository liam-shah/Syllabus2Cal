// Cache keys for TanStack Query, defined in one place. A key identifies a piece of server
// data in the cache; later, editing an event will mark ['events', uploadId] as out of date.

export const queryKeys = {
  authStatus: ['auth-status'] as const,
  events: (uploadId: number) => ['events', uploadId] as const,
}
