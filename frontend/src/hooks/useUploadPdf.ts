import { useMutation } from '@tanstack/react-query'

import { api } from '../api/client'

/**
 * Uploading is a *mutation* (it changes data on the server), not a query: it only runs when
 * the user asks, and its result isn't cached like a read.
 */
export function useUploadPdf() {
  return useMutation({
    mutationFn: (file: File) => api.uploadPdf(file),
  })
}
