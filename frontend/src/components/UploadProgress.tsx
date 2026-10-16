import type { ReactNode } from 'react'

import { useUpload } from '../hooks/useUpload'
import EventReviewTable from './EventReviewTable'

interface UploadProgressProps {
  uploadId: number
}

/** Waits for the background extraction to finish, then shows the events to review. */
export default function UploadProgress({ uploadId }: UploadProgressProps) {
  const upload = useUpload(uploadId)

  if (upload.isPending) return <StatusCard>Loading…</StatusCard>

  if (upload.isError) {
    return (
      <StatusCard>
        <span role="alert" className="text-red-700">
          Couldn't load this upload: {upload.error.message}
        </span>
      </StatusCard>
    )
  }

  switch (upload.data.status) {
    case 'processing':
      return (
        <StatusCard>
          Extracting events from {upload.data.filename} with Claude. This usually takes about a minute,
          and you can refresh the page without losing your place.
        </StatusCard>
      )
    case 'failed':
      return (
        <StatusCard>
          <span role="alert" className="text-red-700">
            Couldn't extract events from {upload.data.filename}: {upload.data.error_message}
          </span>
        </StatusCard>
      )
    case 'extracted':
      return <EventReviewTable uploadId={uploadId} />
  }
}

function StatusCard({ children }: { children: ReactNode }) {
  return (
    // aria-live: screen readers announce the message when it changes (e.g. to an error).
    <section aria-live="polite" className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
      {children}
    </section>
  )
}
