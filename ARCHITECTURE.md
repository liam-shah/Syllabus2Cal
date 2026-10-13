# Architecture

This document explains how Syllabus2Cal is put together and why I made the design
choices I did.

## What the app does

You upload a course schedule or syllabus PDF. The backend pulls the text and tables out of
it, asks Claude to turn them into structured calendar events, and saves them. You review the
events (fix dates, untick ones you don't want), then sync the rest to Google Calendar.

The review step is the core idea. An LLM will sometimes misread a table or guess a date, so
nothing reaches your real calendar until a person has looked at it.

## The big picture: layers

The backend is split into layers, and each layer only talks to the ones below it.

```mermaid
flowchart TD
    Browser["Browser / React frontend"] --> Routers["routers/ - HTTP only"]
    Routers --> Services["services/ - the app's workflows"]
    Services --> Integrations["integrations/ - pdfplumber, Claude, Google"]
    Services --> Models["models.py - database tables"]
```

| Layer | Job | Example |
|---|---|---|
| `routers/` | Read the HTTP request, call a service, return a response | `POST /uploads` reads the file and enforces the 10 MB limit |
| `services/` | The app's own rules and workflows | `UploadService.process_pdf()` - extract, save, handle failures |
| `integrations/` | Wrap someone else's system | `llm_extraction.py` talks to Claude, `google_calendar.py` to Google |
| `models.py` | How data is stored | `Upload`, `ExtractedEvent`, `User` tables |
| `domain.py`, `errors.py` | Types every layer shares | `EventDraft`, `EventStatus`, the exception hierarchy |

The rule is that imports only point *down*. A router can import a service, but a service
never imports a router, and nothing in `integrations/` knows the database exists. In CPSC 210
we talked a lot about **cohesion** (each class/module does one focused job) and **coupling**
(how much modules depend on each other's details). The layers are my way of getting high
cohesion and low coupling: if Google changes its API, only `google_calendar.py` should change.

`domain.py` and `errors.py` sit underneath everything. They don't import FastAPI, SQLAlchemy,
Claude, or Google, so any layer can use them without dragging those libraries along.

## Folder layout

```
backend/app/
  main.py            wires everything together: routers, error handlers, startup
  config.py          settings loaded from .env (API keys, database URL)
  db.py              database engine and sessions
  dependencies.py    FastAPI dependencies: the current user, services
  domain.py          EventDraft + status enums
  errors.py          the exception hierarchy
  models.py          SQLAlchemy tables
  schemas.py         what the API sends back (separate from the tables on purpose)
  routers/           auth.py, upload.py, events.py
  services/          upload_service.py, event_service.py, users.py
  integrations/      pdf_extraction.py, llm_extraction.py, google_calendar.py
```

## Main classes

This is a UML-style class diagram, like the ones we drew in CPSC 210 (only the important
fields are shown).

```mermaid
classDiagram
    class UploadService {
        -Session db
        -User user
        +process_pdf(filename, pdf_bytes) Upload
        +get_upload(upload_id) Upload
        +get_events(upload_id) list~ExtractedEvent~
    }
    class User {
        +int id
        +str google_credentials_json
    }
    class Upload {
        +int id
        +str filename
        +str raw_text
        +UploadStatus status
        +str error_message
    }
    class ExtractedEvent {
        +int id
        +str title
        +date start_date
        +bool date_is_approximate
        +bool included
        +EventStatus status
        +from_draft(draft)$ ExtractedEvent
        +to_draft() EventDraft
        +apply_changes(update)
    }
    class EventService {
        -Session db
        -User user
        +get_event(event_id) ExtractedEvent
        +update_event(event_id, update) ExtractedEvent
    }
    class EventUpdate {
        +str title
        +date start_date
        +bool included
        +changes() dict
    }
    class EventDraft {
        +str title
        +date start_date
        +bool date_is_approximate
        +str start_time
        +str location
        +str source_snippet
    }
    class UploadStatus {
        <<enumeration>>
        EXTRACTED
        FAILED
    }
    class EventStatus {
        <<enumeration>>
        PENDING_REVIEW
        EDITED
        SYNCED
        SYNC_FAILED
    }
    User "1" --> "*" Upload : owns
    Upload "1" *-- "*" ExtractedEvent : contains
    UploadService ..> Upload : creates and reads
    ExtractedEvent ..> EventDraft : converts to/from
    EventService ..> ExtractedEvent : finds and saves
    ExtractedEvent ..> EventUpdate : applies
    Upload --> UploadStatus
    ExtractedEvent --> EventStatus
```

**`EventDraft` vs `ExtractedEvent`.** These look similar but have different jobs.
`EventDraft` is "an event" with no connection to storage: it's what Claude produces and what
the Google Calendar code consumes. `ExtractedEvent` is the database row, which adds things
only storage cares about (an `id`, which upload it belongs to, whether it's been synced). The
row knows how to convert itself (`from_draft` / `to_draft`), so that logic lives with the
data it works on instead of in a separate helper module.

**`UploadService`** is created fresh for every request with the database session and the
current user passed into its constructor. It doesn't create those itself, which is what makes
it easy to test with a throwaway database. **`EventService`** works the same way for editing.
I kept it separate from `UploadService` because "process a PDF" and "review an event" are
different responsibilities, and syncing will get its own service too.

**Where the editing rules live.** The rules for changing an event are a method on the event
itself, `ExtractedEvent.apply_changes()`, not in the service or the router:

- a synced event can't be changed (it's already in Google Calendar)
- changing anything except the include checkbox marks the event `edited`
- choosing a date yourself clears the "approximate" flag
- an end time needs a start time, and can't be before it

It checks everything *before* changing anything, so a rejected edit leaves the event exactly as
it was. This is encapsulation in the CPSC 210 sense: the object protects its own invariants,
so there's no way to edit an event that skips the rules.

**`EventUpdate` vs `EventDraft`.** Both describe event fields, but they come from different
places, so they validate differently. A strange time from Claude (`"2pm"`) is moved into the
description so one bad field can't fail a whole upload. The same value from a person is
rejected with a message they can fix ("Start time: use 24-hour time like 14:00."). `EventUpdate`
also refuses fields it doesn't know about (`extra="forbid"`), so a client can't set things like
`status` or `google_event_id` itself.

## How an upload works

```mermaid
sequenceDiagram
    participant B as Browser
    participant R as upload router
    participant S as UploadService
    participant P as pdf_extraction
    participant C as llm_extraction (Claude)
    participant D as Database
    B->>R: POST /uploads (PDF file)
    R->>R: read at most 10 MB (else 413)
    R->>S: process_pdf(filename, bytes)
    S->>P: extract_text + extract_tables
    Note over S,P: not a PDF -> PDFExtractionError -> 400
    S->>C: extract_events(text, tables)
    C-->>S: list of EventDraft
    Note over S,C: Claude fails -> upload saved as FAILED -> 502
    S->>D: save upload + all events (one transaction)
    S-->>R: Upload
    R-->>B: 201 Created
```

## Error handling

Errors are grouped by *what kind of failure* it is, not by which library failed:

```mermaid
classDiagram
    Exception <|-- AppError
    AppError <|-- NotFoundError
    AppError <|-- InvalidInputError
    AppError <|-- ConflictError
    AppError <|-- ExternalServiceError
    InvalidInputError <|-- PDFExtractionError
    ExternalServiceError <|-- LLMExtractionError
    ExternalServiceError <|-- GoogleCalendarError
```

`main.py` registers one handler for `AppError` and maps each category to an HTTP status
(`NotFoundError` -> 404, `InvalidInputError` -> 400, `ConflictError` -> 409,
`ExternalServiceError` -> 502). When I added `ConflictError` for "you can't edit a synced
event", the only other change needed was one line in that map. This is the
same idea as the exception hierarchies from CPSC 210: code that handles the parent type
automatically handles every subclass. Adding a new error just means picking the right parent,
and no router needs a `try/except`. The error classes themselves don't know about HTTP, so
they could be reused by something that isn't a web server.

## The frontend

The frontend is a React + TypeScript app (built with Vite) in `frontend/`. I split it the same
way as the backend, and again each layer only uses the one below it:

```mermaid
flowchart TD
    Components["components/ - what's on screen"] --> Hooks["hooks/ - what data to load"]
    Hooks --> Client["api/client.ts - every HTTP call"]
    Client --> Backend["FastAPI backend"]
```

| Frontend layer | Backend equivalent | Example |
|---|---|---|
| `components/` | routers | `EventReviewTable` shows the events, plus its loading and error states |
| `hooks/` | services | `useEvents(uploadId)` decides what to load and how it's cached |
| `api/client.ts` | integrations | `api.uploadPdf(file)` - the only place in the frontend that calls `fetch` |
| `types.ts`, `config.ts` | `schemas.py`, `config.py` | the `ExtractedEvent` type, `VITE_API_URL` |

```
frontend/src/
  main.tsx           starts the app and sets up the TanStack Query cache
  App.tsx            puts the page together; remembers which upload is on screen
  config.ts          reads VITE_API_URL once and fails fast if it's missing
  types.ts           the API's data types (mirrors backend/app/schemas.py)
  format.ts, url.ts  small pure helpers (date formatting, state kept in the URL)
  eventForm.ts       the edit form's logic: event -> form values -> only the changed fields
  api/               client.ts (HTTP + ApiError), queryClient.ts (retry rules)
  hooks/             useAuthStatus, useEvents, useUploadPdf, useEventMutations, queryKeys
  components/        AuthStatusBanner, SignInNotice, UploadForm, EventReviewTable, EventRow,
                     EventEditForm
```

A few decisions I'd point out:

- **TanStack Query for server data.** It tracks loading and error state, caches results,
  cancels requests that aren't needed any more, and retries. I set the retry rules myself:
  only retry failures that might be temporary (no connection, or a 5xx), and **never** retry an
  upload automatically, because an upload costs a Claude call and a retry could create a
  duplicate.
- **One error type.** Every failed request becomes an `ApiError` carrying the backend's
  `{"detail": ...}` message, so errors reach the screen in exactly one way.
- **Impossible states can't be represented.** A query's result is *loading*, *error*, or
  *success* - never two at once - and TypeScript only lets a component use the data after it
  has handled the other two. Statuses are string unions (`'pending_review' | 'synced' | ...`)
  that mirror the backend's enums.
- **Some state lives in the URL.** The upload being reviewed is kept as `?upload=3`, so
  refreshing the page doesn't lose it (and doesn't mean paying for another extraction).
- **Dates are parsed carefully.** `new Date("2026-09-15")` means midnight *UTC*, which is still
  Sep 14 in Vancouver, so every date would show a day early. `formatDate` builds the date from
  its parts instead, and the tests run in Vancouver time so this bug can't sneak back in.

### Editing events

- **The include checkbox is optimistic.** It changes the moment you click, before the server
  replies, and rolls back (with a message) if the save fails. On failure it undoes only *that*
  event: restoring a snapshot of the whole list would also undo other boxes ticked meanwhile.
  The checkbox is disabled while its own save is running, so two clicks can't race.
- **The edit form is not optimistic.** It waits for the server, so a validation error can be
  shown inside the form and the form stays open to fix it.
- **Only changed fields are sent.** `buildEventUpdate` compares the form with the event and
  sends just the difference. The request says exactly what the user did, and an untouched field
  can't overwrite a newer value.
- **After a save, only that one event is replaced in the cache**, using the server's copy,
  instead of reloading all ~60 events.
- **Each row owns its own mutations**, so "Saving…" and errors belong to that row. The table
  passes each row its `uploadId`, so rows update the exact cache entry the table reads.

## How the two halves connect

The frontend (port 5173 locally) and backend (port 8000) are different *origins*, so browsers
block the frontend's JavaScript from reading API responses unless the backend allows it. That's
CORS. The backend allows exactly one origin (`FRONTEND_URL`) and only the methods the app uses.
I chose this over a dev proxy because it's how a separately hosted frontend and backend work in
production. Something that surprised me: CORS isn't a firewall - the request still reaches the
server, the browser just won't let another site's JavaScript *read* the response.

Google sign-in is different from the API calls because it's a *page navigation*: the whole
browser goes to Google and back, so the backend answers with redirects instead of JSON.

```mermaid
sequenceDiagram
    participant U as Browser
    participant B as Backend
    participant G as Google
    U->>B: click "Connect Google Calendar" (/auth/google/login)
    B-->>U: redirect to Google (with a state value and a PKCE challenge)
    U->>G: sign in and approve calendar access
    G-->>U: redirect to /auth/google/callback?code=...&state=...
    U->>B: callback
    B->>G: swap the code (plus the PKCE verifier) for tokens
    B-->>U: redirect to the frontend: /?google=connected
```

If anything goes wrong, the callback redirects to `/?google=error&reason=<code>` with a fixed
code like `access_denied`, never raw error text, and the frontend turns the code into a
friendly message.

Every URL that changes between environments is a setting (`FRONTEND_URL`, `BACKEND_URL`,
`VITE_API_URL`), so deploying shouldn't need any code changes. `VITE_` variables end up in the
JavaScript sent to the browser, so they're public and must never hold a secret.

## Design decisions

**Approximate dates start unticked.** When the PDF only gives a week, Claude has to pick a
placeholder day. Those events start excluded, so nothing lands on a guessed day unless I fix the
date or tick it on purpose. The safe choice is the default, but it's only a default.

**One transaction per upload (all or nothing).** An upload and its ~60 events are saved in a
single commit. If something fails halfway, nothing is saved, so there are never half-finished
uploads. The exception is on purpose: when Claude fails, the upload is saved with status
`FAILED` and its raw text, so I can see exactly what Claude was given when I tune the prompt.

**Statuses are enums, checked by the database too.** Statuses like `"synced"` used to be
strings typed out in several files, where a typo would silently match nothing. Now they're
`StrEnum`s defined once in `domain.py`, and the database columns have a `CHECK` constraint,
so even buggy code can't store an unknown status. Two layers of protection for one rule.

**Schemas are separate from models.** The API response types (`schemas.py`) list exactly which
fields leave the server. `raw_text` is never sent back, and no schema includes the user's
Google tokens, so a new route can't leak them by accident.

**Dependency injection for services.** Routes ask FastAPI for what they need
(`Depends(get_upload_service)`) instead of building it. `get_current_user` in
`dependencies.py` is the only place that knows the app currently has one user; supporting
real accounts later means changing that one function.

**Ownership checks return 404, not 403.** `UploadService.get_upload` checks that the upload
belongs to the current user. With one user this never fails, but with many it stops someone
reading other people's uploads by changing the ID in the URL (an "IDOR" bug). Returning 404
means the app doesn't even confirm the upload exists.

**No repository layer (on purpose).** Some architectures put every database query in a
separate repository class. At this size that would just add another layer to click through,
so services use the SQLAlchemy session directly. If the queries grow, that's where I'd split
them out.

## Testing

- Every test gets its own empty in-memory SQLite database (`tests/conftest.py`), so tests can't
  affect each other or my real data.
- Claude and Google are replaced with fakes in unit tests, so tests are fast, free, and don't
  need the internet.
- There are tests at each layer: the domain types, the models (including that the database
  really rejects a bad status), the integrations, and `UploadService`'s whole workflow
  including the failure paths.
- HTTP-level tests go through the real app with FastAPI's `TestClient`, pointed at the test
  database, to check things like the sign-in redirects and that CORS refuses other sites.
- Run them from `backend/` with `pytest`.
- The frontend uses Vitest and React Testing Library. Tests render real components and only
  fake the network (`fetch`), so they check what a user would see rather than internal details.
  Run them from `frontend/` with `npm test`.

## Known limitations and future work

- **Provider interfaces.** The Claude and Google code are plain modules. If I wanted to support
  another calendar (e.g. Outlook) or AI provider, I'd define interfaces like `CalendarProvider`
  and inject the implementation, which would also make the tests less dependent on file paths.
  I left this out for now because I only need one of each.
- **Database migrations.** `create_all` can create tables but can't change existing ones, so a
  schema change currently means recreating the local database. A migration tool (Alembic) is the
  proper fix once there's real data to keep.
- **Slow requests.** Extraction takes around a minute and the browser waits for it. A background
  job with a progress indicator would be a better experience.
- **Table reading.** Claude sometimes misreads which weekday a column belongs to. The review
  step catches this, but improving the prompt is ongoing.
- **Hand-written frontend types.** `types.ts` is kept in sync with the backend by hand. Generating
  it from the backend's OpenAPI schema (`/openapi.json`) would make drift impossible.
- **Syncing.** Events can be reviewed and edited, but syncing them to Google Calendar is the
  next feature.
- **Lost updates.** If the same event were edited in two tabs at once, the last save would win.
  Sending only changed fields makes this much less likely, and a version number checked on each
  save (optimistic locking) would rule it out if it ever mattered.
