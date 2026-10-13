import { useState, type FormEvent } from 'react'

import { useUploadPdf } from '../hooks/useUploadPdf'
import type { Upload } from '../types'

interface UploadFormProps {
  /** Called once the backend has extracted the events, so the parent can show them. */
  onUploaded: (upload: Upload) => void
}

export default function UploadForm({ onUploaded }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null)
  const upload = useUploadPdf()

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault() // stop the browser's default full-page form submission
    if (file === null) return
    // Pass on only the upload: TanStack's onSuccess gets extra arguments the parent shouldn't depend on.
    upload.mutate(file, { onSuccess: (createdUpload) => onUploaded(createdUpload) })
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">Upload a schedule</h2>
      <p className="mt-1 text-sm text-slate-600">
        A course schedule or syllabus PDF, up to 10 MB. You'll review the events before anything is
        added to your calendar.
      </p>

      <form onSubmit={handleSubmit} className="mt-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="pdf-file" className="text-sm font-medium text-slate-700">
            PDF file
          </label>
          <input
            id="pdf-file"
            type="file"
            accept="application/pdf,.pdf"
            disabled={upload.isPending}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-200"
          />
        </div>
        <button
          type="submit"
          disabled={file === null || upload.isPending}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {upload.isPending ? 'Extracting…' : 'Extract events'}
        </button>
      </form>

      {/* aria-live: screen readers announce these messages when they appear. */}
      <div aria-live="polite" className="mt-3 text-sm">
        {upload.isPending && (
          <p className="text-slate-600">
            Reading your PDF and extracting events with Claude. This usually takes about a minute.
          </p>
        )}
        {upload.isError && (
          <p role="alert" className="text-red-700">
            {upload.error.message}
          </p>
        )}
      </div>
    </section>
  )
}
