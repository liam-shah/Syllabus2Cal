import { useId, useState, type FormEvent, type ReactNode } from 'react'

import { buildEventUpdate, toFormValues, type EventFormValues } from '../eventForm'
import type { EventUpdate, ExtractedEvent } from '../types'

interface EventEditFormProps {
  event: ExtractedEvent
  isSaving: boolean
  error: string | null
  /** Called with only the fields that changed (possibly none). */
  onSave: (changes: EventUpdate) => void
  onCancel: () => void
}

/** Edits one event. Holds the in-progress values; the parent decides what saving means. */
export default function EventEditForm({ event, isSaving, error, onSave, onCancel }: EventEditFormProps) {
  // The form's own state: what the user has typed so far, separate from the saved event.
  const [values, setValues] = useState<EventFormValues>(() => toFormValues(event))
  const id = useId() // unique per row, so every label points at the right input

  function setValue<K extends keyof EventFormValues>(field: K, value: EventFormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  function handleSubmit(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault()
    onSave(buildEventUpdate(event, values))
  }

  const inputClass = 'rounded-md border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100'

  return (
    <form onSubmit={handleSubmit} aria-label={`Edit ${event.title}`} className="space-y-3 py-1">
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Date" htmlFor={`${id}-date`}>
          <input
            id={`${id}-date`}
            type="date"
            required
            value={values.startDate}
            disabled={isSaving}
            // Choosing a date makes it exact - the same rule the backend applies.
            onChange={(e) => setValues((current) => ({ ...current, startDate: e.target.value, dateIsApproximate: false }))}
            className={inputClass}
          />
        </Field>
        <Field label="Start time" htmlFor={`${id}-start`}>
          <input id={`${id}-start`} type="time" value={values.startTime} disabled={isSaving}
            onChange={(e) => setValue('startTime', e.target.value)} className={inputClass} />
        </Field>
        <Field label="End time" htmlFor={`${id}-end`}>
          <input id={`${id}-end`} type="time" value={values.endTime} disabled={isSaving}
            onChange={(e) => setValue('endTime', e.target.value)} className={inputClass} />
        </Field>
        <label className="flex items-center gap-2 self-end pb-1 text-sm text-slate-700">
          <input type="checkbox" checked={values.dateIsApproximate} disabled={isSaving}
            onChange={(e) => setValue('dateIsApproximate', e.target.checked)} />
          Date is approximate
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Title" htmlFor={`${id}-title`}>
          <input id={`${id}-title`} type="text" required value={values.title} disabled={isSaving}
            onChange={(e) => setValue('title', e.target.value)} className={inputClass} />
        </Field>
        <Field label="Location" htmlFor={`${id}-location`}>
          <input id={`${id}-location`} type="text" value={values.location} disabled={isSaving}
            onChange={(e) => setValue('location', e.target.value)} className={inputClass} />
        </Field>
      </div>

      <Field label="Description" htmlFor={`${id}-description`}>
        <textarea id={`${id}-description`} rows={2} value={values.description} disabled={isSaving}
          onChange={(e) => setValue('description', e.target.value)} className={inputClass} />
      </Field>

      {error !== null && (
        <p role="alert" className="text-sm text-red-700">{error}</p>
      )}

      <div className="flex gap-2">
        <button type="submit" disabled={isSaving}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onCancel} disabled={isSaving}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
          Cancel
        </button>
      </div>
    </form>
  )
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-xs font-medium text-slate-600">{label}</label>
      {children}
    </div>
  )
}
