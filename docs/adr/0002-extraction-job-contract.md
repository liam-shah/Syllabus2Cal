# 2. The extraction job gets only an upload id, and claims the upload once

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Extraction (the Claude call) takes about a minute, so it runs after the upload request has
answered. Until now that was a FastAPI `BackgroundTask`, which received the PDF's bytes in
memory. Before deploying, it moves to Cloud Tasks (ADR 3 and 4 cover the worker endpoint and
the queue). That changes two things:

- **The job can't carry the PDF.** A Cloud Task's body is capped at about 1 MB, and uploads
  can be 10 MB.
- **Jobs can run more than once.** Cloud Tasks retries a task when it doesn't get a 2xx. A
  retry after Claude has already answered would pay for Claude a second time.

## Decision

1. **Everything Claude needs is saved at upload time.** `start_upload` already saved the PDF's
   text. Now it also saves the tables (`uploads.tables_json`). The job's input is just
   `upload_id`. The PDF itself is never stored.
2. **The job claims the upload with a compare-and-set** before calling Claude:

   ```sql
   UPDATE uploads SET extraction_claimed_at = now
   WHERE id = ? AND status = 'processing' AND extraction_claimed_at IS NULL
   ```

   Only the run whose UPDATE changes the row continues. Every other run, whether a retry, a
   duplicate delivery or a job arriving after the upload was given up on, returns without
   calling Claude. `run_extraction` returns whether it ran, so the worker endpoint can tell the
   queue "done, don't retry" in both cases.

## Alternatives considered

| Option | Why not |
|---|---|
| Store the PDF in Cloud Storage and pass its path | A second service to set up, secure and clean up, just to re-read bytes that `start_upload` has already read. Text plus tables are a few KB. |
| A separate "extracting" status instead of a timestamp | It changes the `upload_status` CHECK constraint again, and the frontend's status union, for something only the backend cares about. A nullable timestamp is additive. |
| Rely on Cloud Tasks delivering each task once | It promises at least once, not exactly once, and the duplicate costs real money. |

## Consequences

- Table extraction moves into the upload request. It's quick for a schedule (and capped by the
  50,000-character text limit), and a PDF whose tables can't be read now gets a 400
  immediately, instead of an upload that fails later.
- A run that claims an upload and then crashes leaves it `processing`. The existing 15-minute
  give-up in `get_upload` still marks it failed, because that only checks `status`.
- Uploads from before this change have no `tables_json`. They're all finished, but the job
  treats a missing value as "no tables" anyway.
