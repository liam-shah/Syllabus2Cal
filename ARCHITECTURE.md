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
  services/          upload_service.py, users.py
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
it easy to test with a throwaway database.

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
    AppError <|-- ExternalServiceError
    InvalidInputError <|-- PDFExtractionError
    ExternalServiceError <|-- LLMExtractionError
    ExternalServiceError <|-- GoogleCalendarError
```

`main.py` registers one handler for `AppError` and maps each category to an HTTP status
(`NotFoundError` -> 404, `InvalidInputError` -> 400, `ExternalServiceError` -> 502). This is the
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
  api/               client.ts (HTTP + ApiError), queryClient.ts (retry rules)
  hooks/             useAuthStatus, useEvents, useUploadPdf, queryKeys
  components/        AuthStatusBanner, SignInNotice, UploadForm, EventReviewTable, EventRow
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
- **Editing and syncing.** The review table is read-only for now; editing events and syncing them
  to Google Calendar are the next features.
