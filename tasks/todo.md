# Tasks: Deploy Syllabus2Cal

Plan and decisions: [plan.md](plan.md). Commands assume the backend venv is active.
- Backend tests: `cd backend && python -m pytest -q`
- Backend on Postgres: `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest -q`
- Frontend: `cd frontend && npm test && npm run lint && npm run build`

Project-wide Definition of Done for every task:
- tests pass
- no regressions
- behaviour checked at runtime
- docs and ADRs updated

---

## Phase 1: Foundation: correct on Postgres

### Task 1: Backend runs and passes its tests on Postgres

**Description:** Add a Postgres driver and Postgres-friendly engine settings. Let the test
suite run against any database given in `TEST_DATABASE_URL` (SQLite in memory stays the
default). Then fix whatever breaks. The likely breakages:
- the `upload_status` CHECK constraint in migration `7339f928223f`, which batch mode only
  rebuilds on SQLite
- `test_migrations.py` inserting `1`/`0` into boolean columns

Do this first: it's the riskiest unknown, and everything after builds on it.

**Prerequisite (you):** install Docker Desktop with the WSL 2 backend; it isn't on this
machine yet. Then start the test database:
`docker run -d --name s2c-postgres -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16`.
Test URL: `postgresql+psycopg://postgres:dev@localhost:5432/postgres`.

**Acceptance criteria:**
- [x] `alembic upgrade head` then `downgrade base` works on an empty Postgres database, and
  `'processing'` can be stored in `uploads.status`
- [x] The whole backend suite passes with `TEST_DATABASE_URL` pointed at Postgres, and still
  passes on SQLite with it unset
- [x] Postgres engines use `pool_pre_ping=True` (Neon pauses idle connections). ADR
  `docs/adr/0001-neon-postgres.md` is written.

**Verification:**
- [x] Tests pass: `python -m pytest -q` (SQLite) and with `TEST_DATABASE_URL` set (Postgres)
- [x] Manual check: `DATABASE_URL=<postgres> alembic upgrade head`, then `uvicorn app.main:app`
  starts without the "database is behind" error

**Dependencies:** None

**Files likely touched:**
- `backend/requirements.txt` (`psycopg[binary]`)
- `backend/app/db.py`
- `backend/tests/conftest.py`
- `backend/tests/test_migrations.py`
- `backend/migrations/versions/7339f928223f_add_processing_upload_status.py`, if the constraint
  isn't replaced on Postgres

**Estimated scope:** M

---

### Task 2: Reject PDFs with no readable text

**Description:** `start_upload` checks for too much text but never for none. A scanned PDF
gets saved, uses up a daily slot, pays for a Claude call and then shows "No events found".
Reject it before anything is saved, with a message that suggests the cause.

**Acceptance criteria:**
- [x] A PDF whose text is empty or only whitespace gets a 400 saying it looks like a scanned
  image, and Claude is never called
- [x] Nothing is saved, so the daily limit doesn't count it

**Verification:**
- [x] Tests pass: `python -m pytest -q tests/test_upload_service.py tests/test_upload_routes.py`
  (the test uses a real image-only PDF; 154 pass on SQLite and Postgres)
- [ ] Manual check: upload a PDF made from an image; the form shows the message
  *(not done yet: needs your Google sign-in in the browser)*

**Dependencies:** None

**Files likely touched:**
- `backend/app/services/upload_service.py`
- `backend/tests/test_upload_service.py`

**Estimated scope:** XS

---

### Task 3: Two syncs at once can't create duplicate calendar events

**Description:** `ensure_sync_key` decides in Python whether a key exists. When two syncs
run at the same moment, each sees `NULL`, each saves a different key, and Google creates the
event twice. Replace it with an atomic database claim,
`UPDATE ... SET sync_key=:new WHERE id=:id AND sync_key IS NULL`, then use whatever key
the database actually holds.

**Acceptance criteria:**
- [x] If another session saves a key after this one loaded the event, sync uses the stored
  key instead of creating a new one (test with two sessions on the same database)
- [x] Retries and existing sync behaviour are unchanged (current `test_sync_service.py` passes)

**Verification:**
- [x] Tests pass on SQLite and on Postgres: `python -m pytest -q tests/test_sync_service.py tests/test_models.py`
  (155 pass on each)
- [ ] Manual check: two tabs press Sync together → each event appears once in Google Calendar
  *(not done yet: needs your Google account; covered again in Checkpoint 3)*

**Dependencies:** Task 1, so the compare-and-set is proven on Postgres

**Files likely touched:**
- `backend/app/models.py` (`ensure_sync_key`)
- `backend/app/services/sync_service.py`
- `backend/tests/test_sync_service.py`

**Estimated scope:** S

---

### Task 4: Events sync in the user's own timezone

**Description:** `TIMEZONE = "America/Vancouver"` is hardcoded. Decided: the timezone comes
from the browser on each sync. The frontend sends the browser's IANA timezone (`Intl.DateTimeFormat().resolvedOptions().timeZone`) with each sync.
The backend checks it with `zoneinfo` and passes it to `build_event_body`. Add `tzdata`,
because Windows and slim Linux images have no timezone database.

**Acceptance criteria:**
- [x] `POST /events/sync?upload_id=&time_zone=America/Toronto` creates timed events in
  Toronto time; all-day events are unaffected
- [x] An unknown timezone gets a 422 before Google is contacted (FastAPI's validation status,
  like the edit form's; the frontend shows it as a readable sentence)
- [x] The frontend always sends the browser's timezone

**Verification:**
- [x] Tests pass: `python -m pytest -q tests/test_google_calendar.py tests/test_sync_service.py tests/test_event_routes.py`
- [x] Tests pass: `npm test` (`client.test.ts` checks the query string)
- [ ] *(not done yet: needs your Google account)* Manual check: set the OS timezone to Toronto, sync a 09:00 lecture, and Google
  Calendar shows 09:00 Toronto time

**Dependencies:** Task 3 (same file: `sync_service.py`)

**Files likely touched:**
- `backend/app/integrations/google_calendar.py`
- `backend/app/services/sync_service.py`
- `backend/app/routers/events.py`
- `backend/requirements.txt`
- `frontend/src/api/client.ts` and its test

**Estimated scope:** M

---

### Checkpoint 1: Foundation
- [ ] Backend suite passes on SQLite **and** Postgres; `npm test && npm run lint && npm run build` pass
- [ ] Local app works end to end (upload → review → sync) with `DATABASE_URL` pointed at Postgres
- [ ] Review with human before Phase 2

---

## Phase 2: Extraction moves off the web server

### Task 5: The extraction job needs only `upload_id`, and claims the upload exactly once

**Description:** Pull the tables out at upload time, in `start_upload` next to `extract_text`,
and store them as JSON on the upload. Add an `extraction_claimed_at` column. The job becomes
`run_extraction(session_factory, upload_id)`:
- it claims the upload with `UPDATE ... SET extraction_claimed_at=now WHERE id=? AND
  status='processing' AND extraction_claimed_at IS NULL`
- it does nothing if the claim fails
- otherwise it runs `extract_events` from the stored text and tables

The local BackgroundTasks path calls this same function, so the PDF bytes are no longer
needed once the request ends.

**Acceptance criteria:**
- [x] The background job receives only `upload_id`; the PDF bytes aren't kept after the request
- [x] Running the job twice for one upload calls Claude once (test with the fake LLM)
- [x] A new Alembic migration adds `tables_json` and `extraction_claimed_at` (both nullable).
  `test_migrations` passes on both databases. ADR `docs/adr/0002-extraction-job-contract.md`
  covers the payload limit and the claim.

**Verification:**
- [x] Tests pass on both databases: `python -m pytest -q`
- [x] Manual check: upload locally; it goes from processing to extracted as before
  (run against the s2c_dev Postgres with Claude faked: 2,288 chars of tables saved; two runs, one Claude call)

**Dependencies:** Task 1

**Files likely touched:**
- `backend/app/models.py`
- `backend/migrations/versions/<new>_add_extraction_claim.py`
- `backend/app/services/upload_service.py`
- `backend/app/routers/upload.py`
- `backend/tests/test_upload_service.py`

**Estimated scope:** M

---

### Task 6: A worker endpoint that only accepts calls from Cloud Tasks

**Description:** Add `POST /internal/extractions/{upload_id}` to the existing service. It
calls `run_extraction`. It runs only if the request carries a Google-signed token
(`Authorization: Bearer`), checked with `id_token.verify_oauth2_token`:
- the audience is the service's own URL (`SERVICE_URL`)
- `email` is the tasks service account (`TASKS_SERVICE_ACCOUNT`)
- `email_verified` is true

Anything else gets 401 before any database work. The token checker is its own dependency, so
tests swap in a fake one. If both settings are unset (local dev), the route is disabled and
returns 404. Responses:
- an unexpected error marks the upload failed and returns 500
- a claim that's already taken returns 204, so Cloud Tasks stops retrying

**Acceptance criteria:**
- [x] With a valid token, the route runs extraction and returns 2xx, including when Claude fails
  (the upload is marked failed and that's the end of it)
- [x] A missing token, wrong audience, wrong service-account email or unverified email each get
  401 and never touch the upload (one test each); the route returns 404 when it isn't configured
- [x] ADR `docs/adr/0003-worker-endpoint-auth.md` (one service with the token checked in the
  app, versus a separate service only Google can reach)

**Verification:**
- [x] Tests pass: `python -m pytest -q tests/test_worker_routes.py` (179 pass on SQLite and Postgres)
- [x] Local runtime check with the real Google verifier: unconfigured → 404, no token → 401,
  garbage token → 401, the normal API is unaffected
- [ ] Manual check (after Task 9): `curl -X POST https://<service>.run.app/internal/extractions/1`
  with no token → 401

**Dependencies:** Task 5

**Files likely touched:**
- `backend/app/routers/worker.py` (new)
- `backend/app/integrations/cloud_tasks.py` (new; the token check lives here)
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/tests/test_worker_routes.py` (new)

**Estimated scope:** M

---

### Task 7: In production, uploads queue a Cloud Task instead of a BackgroundTask

**Description:** When `CLOUD_TASKS_QUEUE` is set (along with Task 6's `SERVICE_URL` and
`TASKS_SERVICE_ACCOUNT`), `POST /uploads` creates an HTTP Cloud Task. The task POSTs to
`{SERVICE_URL}/internal/extractions/{id}`: the `run.app` URL directly, never through Firebase,
whose 60-second limit would cut Claude off. It carries a Google-signed token for the tasks
service account, with the audience set to `SERVICE_URL`. Call the Cloud Tasks REST API through google-auth's
`AuthorizedSession` (already installed), not a new SDK. With the settings unset, the route
keeps using BackgroundTasks, so local dev needs no Google Cloud. The queueing step is a
dependency, so tests swap in a fake. If queueing raises, the upload is marked `FAILED` with
a "please try again" message. This removes the `shortcut:` comment in `extract_in_background`.

**Acceptance criteria:**
- [ ] With the queue configured, an upload creates exactly one task that targets
  `SERVICE_URL`, has an OIDC audience of `SERVICE_URL` and carries only the upload id
  (checked with a fake queue)
- [ ] With the queue unset, behaviour is identical to today (existing upload route tests pass)
- [ ] A queueing failure leaves the upload `FAILED`, not stuck processing

**Verification:**
- [ ] Tests pass on both databases: `python -m pytest -q`
- [ ] Manual check (after Task 9): the Cloud Tasks console shows the task dispatched with a
  2xx response

**Dependencies:** Task 6

**Files likely touched:**
- `backend/app/integrations/cloud_tasks.py` (queueing added next to Task 6's token check)
- `backend/app/dependencies.py`
- `backend/app/routers/upload.py`
- `backend/app/config.py`
- `backend/tests/test_upload_routes.py`

**Estimated scope:** M

---

### Checkpoint 2: Production-shaped backend
- [ ] Local dev works with no Google Cloud settings (falls back to BackgroundTasks)
- [ ] Backend suite green on both databases; frontend checks green
- [ ] Review with human before the first deploy

---

## Phase 3: First deploy (by hand)

### Task 8: Production container, with the backend served under `/api`

**Description:**
- Add `backend/Dockerfile`: Python 3.13 slim, without the test dependencies (split out
  `requirements-dev.txt`).
- Run uvicorn with `--root-path /api` so Firebase's `/api/**` forward matches the existing
  routes. Check that Starlette strips the root path when matching routes; if it doesn't,
  mount `app` under `/api` in a small parent app. Requests from the browser arrive as
  `/api/...` through Firebase, but Cloud Tasks calls `/internal/...` on `run.app` with no
  prefix. Both must route correctly.
- Add `firebase.json`: hosting from `frontend/dist`, with `/api/**` forwarded to the Cloud
  Run service in us-west1.
- Add `frontend/.env.production` with `VITE_API_URL=/api`.

**Acceptance criteria:**
- [ ] `docker build` succeeds. The container serves `GET /api/auth/status` (the Firebase
  path), and `POST /internal/extractions/1` with no prefix gets the route's 401 (the Cloud
  Tasks path), not a 404.
- [ ] The production frontend build calls the same-origin `/api/...`, and sign-in links point to
  `/api/auth/google/login`
- [ ] ADR `docs/adr/0004-same-origin-api.md` (the cookie, the Firebase rewrite, why CORS no
  longer matters in production)

**Verification:**
- [ ] Build succeeds: `docker build -t s2c backend` and `npm run build`
- [ ] Manual check: run the container locally with a Postgres URL;
  `curl localhost:8080/api/auth/status` returns `{"signed_in": false}`

**Dependencies:** Tasks 4 and 7

**Files likely touched:**
- `backend/Dockerfile` (new)
- `backend/requirements-dev.txt` (new)
- `firebase.json` (new)
- `frontend/.env.production` (new)

**Estimated scope:** M

---

### Task 9: Cloud setup runbook, and the first deploy by hand

**Description:** Write `docs/deploy.md` as a copy-paste runbook, then follow it once. Steps:
1. Firebase project on the Blaze plan, with a **$5 budget alert**.
2. Enable the APIs: Run, Tasks, Secret Manager, Artifact Registry.
3. Neon project in us-west-2.
4. Secrets: Anthropic key, session secret, database URL, `client_secret.json` (mounted as a file).
5. Service accounts: the service's runtime account, plus a tasks account whose identity
   the tasks carry. The runtime account needs `iam.serviceAccountUser` on the tasks account
   to create tasks as it.
6. Cloud Tasks queue with `max-attempts=3`.
7. Artifact Registry with a cleanup policy.
8. Deploy the single `api` service: public, `max-instances` capped, a 15-minute request
   timeout (so the worker route outlives Claude), and `SERVICE_URL` set to its own `run.app` URL.
9. `alembic upgrade head`.
10. `firebase deploy --only hosting`.
11. Add `https://<site>.web.app/api/auth/google/callback` to the OAuth client.
12. Add test users.

Also answer: does `*.web.app` qualify as the homepage for Google verification?

**Acceptance criteria:**
- [ ] The live URL serves the app and you can sign in with Google
- [ ] Every command in `docs/deploy.md` is the one that was actually run (no secrets in the repo)
- [ ] The verification-domain question is answered in `docs/deploy.md`

**Verification:**
- [ ] Manual check: the full flow on your phone (see Checkpoint 3)

**Dependencies:** Task 8

**Files likely touched:**
- `docs/deploy.md` (new)

**Estimated scope:** M (mostly console and CLI work by you; the agent drafts the runbook)

---

### Checkpoint 3: Live smoke test (on your phone)
- [ ] Sign in, upload a real schedule, review, sync: the events appear in Google Calendar
- [ ] Redeploy mid-extraction: the upload finishes, or fails with a message (never stuck)
- [ ] `curl` the worker route on `run.app` with no token → 401
- [ ] Two tabs pressing Sync at once: no duplicate events
- [ ] A scanned PDF gets the clear 400; a second Google test user can sign in
- [ ] The billing page shows about $0 apart from Claude; the budget alert is active
- [ ] Review with human before automating

---

## Phase 4: Automate and document

### Task 10: CI runs every check on every PR

**Description:** `.github/workflows/ci.yml` runs on pull requests and on pushes to master. It
has three jobs:
- backend on SQLite
- backend on a `postgres:16` service container (`TEST_DATABASE_URL`)
- frontend test, lint and build

**Acceptance criteria:**
- [ ] A PR shows three green checks; a failing test turns its job red
- [ ] Dependencies are cached (pip and npm), so repeat runs are faster

**Verification:**
- [ ] Manual check: open a PR with a deliberately failing test → red; revert → green

**Dependencies:** Task 1. This can start any time after Task 1.

**Files likely touched:**
- `.github/workflows/ci.yml` (new)

**Estimated scope:** S

---

### Task 11: Merging to master migrates and deploys automatically

**Description:** `.github/workflows/deploy.yml` runs on pushes to master after CI passes. It
signs in to Google through Workload Identity Federation (`google-github-actions/auth`; one-time
pool and provider setup added to `docs/deploy.md`). Then it:
1. builds and pushes the image to Artifact Registry
2. updates and **executes a `migrate` Cloud Run Job** (`alembic upgrade head`, database URL
   from Secret Manager)
3. deploys the `api` service from that image digest
4. runs `firebase deploy --only hosting`

**Acceptance criteria:**
- [ ] Merging a PR deploys it with no manual steps; a failed migration stops the deploy before
  any service changes
- [ ] There are no service-account JSON keys or database passwords in GitHub secrets (only WIF
  provider and service account names)
- [ ] ADR `docs/adr/0005-keyless-ci-cd.md` (WIF, and migrations as a Cloud Run Job)

**Verification:**
- [ ] Manual check: merge a visible change (e.g. footer text) → it's live within one workflow run
- [ ] Manual check: a migration that's broken on purpose in a test branch fails the job, and
  the live site stays on the previous version

**Dependencies:** Task 9, Task 10

**Files likely touched:**
- `.github/workflows/deploy.yml` (new)
- `docs/deploy.md`

**Estimated scope:** M

---

### Task 12: README setup, ARCHITECTURE.md deployment section, known limitations

**Description:** The README is 3 lines today. Add:
- what the app does
- the live URL
- local setup for the backend and frontend (`.env`, `client_secret.json`, `alembic upgrade
  head`, the dev servers)
- how to run the tests
- a CI badge
- links to ARCHITECTURE.md and `docs/adr/`

In ARCHITECTURE.md:
- add a "Deployment" section with a diagram: Firebase → Cloud Run api → Neon, plus
  Cloud Tasks → worker
- update "How an upload works" for the queue
- update "Known limitations": remove the background-task and SQLite items; add the 60-second
  sync limit and the Testing-mode user cap

**Acceptance criteria:**
- [ ] A fresh clone can be run locally by following only the README
- [ ] ARCHITECTURE.md matches the deployed system (no mentions of BackgroundTasks as the
  production path)
- [ ] `docs/adr/` has an index listing ADRs 0001-0005

**Verification:**
- [ ] Manual check: follow the README in a fresh clone; the app starts and the tests pass

**Dependencies:** Task 11

**Files likely touched:**
- `README.md`
- `ARCHITECTURE.md`
- `docs/adr/README.md` (new)

**Estimated scope:** S

---

### Checkpoint: Complete
- [ ] Merging a PR deploys it with no manual steps
- [ ] ADRs 0001-0005 exist and match what was built
- [ ] README alone gets a new contributor running locally
- [ ] Going public needs only Google verification (privacy policy, homepage, demo video)
