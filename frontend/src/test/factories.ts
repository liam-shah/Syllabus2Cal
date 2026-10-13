import type { ExtractedEvent, Upload } from '../types'

/** A complete event with sensible defaults; tests override only the fields they care about. */
export function makeEvent(overrides: Partial<ExtractedEvent> = {}): ExtractedEvent {
  return {
    id: 1,
    upload_id: 1,
    title: 'Lecture 1b: Pointers',
    start_date: '2026-10-01',
    date_is_approximate: false,
    start_time: null,
    end_time: null,
    location: null,
    description: null,
    source_snippet: '1b: Pointers',
    included: true,
    status: 'pending_review',
    google_event_id: null,
    sync_error: null,
    ...overrides,
  }
}

export function makeUpload(overrides: Partial<Upload> = {}): Upload {
  return {
    id: 7,
    filename: 'cpsc213.pdf',
    status: 'extracted',
    error_message: null,
    created_at: '2026-10-10T18:00:00',
    ...overrides,
  }
}
