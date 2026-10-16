# Implementation Plan: Deploy Syllabus2Cal (public-ready, ~$0/month)

## Overview

Put Syllabus2Cal on a live URL that you and invited friends use the way real users would,
while the Google OAuth app stays in **Testing mode**. The build has to be technically ready
for the public: opening sign-ups should need only Google's verification paperwork (privacy
policy, homepage, demo video), with no code changes. Monthly cost should be about $0 apart
from Claude calls, and each deploy decision gets an ADR so the work also serves as
portfolio material.

**Target stack:**
- Firebase Hosting serves the frontend and forwards `/api/**` to a Cloud Run **API** service.
- Extraction is a Cloud Task that calls an internal route on the **same** Cloud Run service.
  The task goes straight to the service's `run.app` URL, not through Firebase, so Firebase's
  60-second limit doesn't apply. The app checks the Google-signed token on every call.
- Neon Postgres (free tier) replaces SQLite.
- Secrets live in Secret Manager.
- GitHub Actions tests every PR and deploys on merge, signing in to Google with Workload
  Identity Federation (no JSON keys).

Tasks are in [todo.md](todo.md). Each one there has acceptance criteria, verification steps,
dependencies and the files it touches.

## Architecture Decisions

Each decision becomes an ADR in `docs/adr/` in the task that makes it.

| # | Decision | Why | Recorded in |
|---|---|---|---|
| 1 | **Neon Postgres (free tier)**, not Cloud SQL, Firestore or SQLite on a volume | Cloud SQL costs about $10 a month while idle. Firestore would mean rewriting the SQLAlchemy, Alembic and CHECK-constraint layer. Cloud Run doesn't keep files on disk. Neon is standard Postgres at $0. | Task 1 |
| 2 | **The worker job is given only `upload_id`.** Tables are pulled out of the PDF at upload time and saved as JSON. | A Cloud Task's payload is capped at about 1 MB and PDFs can be 10 MB. `extract_events` only needs the text and tables, so the PDF bytes don't have to survive the request. No Cloud Storage needed. | Task 5 |
| 3 | **The worker claims the upload with compare-and-set** (`extraction_claimed_at`) | Cloud Tasks retries failed jobs. Without a claim, a retry after Claude has answered pays for Claude twice. Same pattern as `_give_up_on`. | Task 5 |
| 4 | **One Cloud Run service. The worker route checks the Cloud Tasks token in the app** (Google's signature, audience = the service URL, email = the tasks service account) | One service to deploy, configure and pay for. It reuses `id_token.verify_oauth2_token`, which sign-in already uses. The trade-off: the route is reachable from the internet, so the check is security-critical and needs a test for each way it can be refused. The alternative was a second service that only Google's own sign-in can reach. | Task 6 |
| 5 | **Same origin through a Firebase rewrite.** The backend serves under `/api`; `VITE_API_URL=/api` | The `__session` cookie only gets through Firebase Hosting, and keeping it first-party sidesteps the SameSite and third-party cookie problems. CORS stays configured but isn't needed in production. | Task 8 |
| 6 | **Migrations run as a Cloud Run Job before each deploy** (the job uses the service's image) | The database password stays in Secret Manager instead of GitHub secrets. The same image runs the same Alembic. | Task 11 |
| 7 | **Keyless CI/CD through Workload Identity Federation** | No long-lived service-account key to leak or rotate. | Task 11 |
| 8 | **Timezone comes from the browser on each sync**, passed to Google as an IANA name and checked against `zoneinfo` | Stateless and right for the person syncing. Being checked on the way in, a bad value can't fail every event in a sync. | Task 4 |

Region: **us-west1 (Oregon)** for Cloud Run and Cloud Tasks, with Neon in **AWS us-west-2
(Oregon)**. That keeps database round trips short and is close to Vancouver.

## Task List

### Phase 1: Foundation: correct on Postgres
- [x] Task 1: Backend runs and passes its tests on Postgres *(highest risk, so it goes first)*
- [x] Task 2: Reject PDFs with no readable text
- [x] Task 3: Two syncs at once can't create duplicate calendar events
- [x] Task 4: Events sync in the user's own timezone

### Checkpoint 1: Foundation
- [ ] Backend suite passes on SQLite **and** on Postgres; frontend test, lint and build pass
- [ ] Local app works end to end (upload → review → sync) against a Postgres database
- [ ] Review with human

### Phase 2: Extraction moves off the web server
- [x] Task 5: The extraction job needs only `upload_id`, and claims the upload exactly once
- [x] Task 6: A worker endpoint that only accepts calls from Cloud Tasks
- [ ] Task 7: In production, uploads queue a Cloud Task instead of a BackgroundTask

### Checkpoint 2: Production-shaped backend
- [ ] Local dev still works with no Google Cloud (it falls back to BackgroundTasks)
- [ ] Both suites green on both databases
- [ ] Review with human

### Phase 3: First deploy (by hand)
- [ ] Task 8: Production container, with the backend served under `/api`
- [ ] Task 9: Cloud setup runbook, and the first deploy by hand

### Checkpoint 3: Live smoke test (on your phone)
- [ ] Sign in, upload a real schedule, review, sync: the events appear in Google Calendar
- [ ] Redeploy mid-extraction: the upload still finishes or fails cleanly (never stuck)
- [ ] `curl` the worker route on `run.app` with no token → 401
- [ ] Two tabs pressing Sync at once: no duplicate events
- [ ] A scanned PDF gets a clear 400; a second Google account added as a test user can sign in
- [ ] The billing page shows about $0 (Claude aside), and the budget alert is set
- [ ] Review with human

### Phase 4: Automate and document
- [ ] Task 10: CI runs every check on every PR
- [ ] Task 11: Merging to master migrates and deploys automatically
- [ ] Task 12: README setup, ARCHITECTURE.md deployment section, known limitations

### Checkpoint: Complete
- [ ] Merging a PR deploys it with no manual steps
- [ ] Each decision in the table above has an ADR
- [ ] A new contributor can run the app locally from the README alone
- [ ] The only remaining step to go public is Google verification

## Dependency Graph

```
Task 1 Postgres ──┬── Task 3 sync race (CAS tested on Postgres) ── Task 4 timezone (same file: sync_service.py)
                  ├── Task 5 job needs only upload_id ── Task 6 worker route ── Task 7 Cloud Tasks enqueue
                  └── Task 10 CI (needs the Postgres test mode)
Task 2 empty PDF  (independent)
Tasks 4, 7 ── Task 8 container + /api ── Task 9 first deploy ── Task 11 CD ── Task 12 docs
```

## Parallelization

- **Can run in parallel after Task 1:** Task 2, Task 3 then 4 (one chain, because both touch
  `sync_service.py`), Task 5 then 6 then 7 (one chain), and Task 10.
- **Must be sequential:** the migrations in Tasks 1 and 5, and everything from Task 8 on.
  Each step there needs live infrastructure from the step before.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ~~Migration `7339f928223f` leaves the old `upload_status` CHECK constraint on Postgres~~ **Resolved in Task 1:** the constraint is replaced correctly; a test covers it on both databases | — | Task 1 runs `test_migrations.py` on Postgres first. If it fails, add a Postgres-only drop-and-recreate of the constraint inside that migration. Neon starts empty, so no existing data needs fixing. |
| The worker route is public, so a token check that's too loose lets anyone trigger extraction | Med (the claim limits harm: each processing upload runs at most once, and nothing is read or returned) | Task 6 tests a missing token, the wrong audience, the wrong service-account email and an unverified email. The token checker is a dependency so tests can fake it. |
| Docker isn't installed on this machine yet | Blocks Tasks 1 and 8 locally | Install Docker Desktop (with WSL 2) before Task 1. CI uses its own Postgres service container regardless. |
| A Cloud Tasks retry pays for Claude twice | High (money) | Compare-and-set claim (Task 5), `max-attempts` kept low on the queue (Task 9), plus a unit test for an upload that's already claimed |
| Queueing the task fails after the upload was saved: it uses a daily slot and sits in "processing" | Med | Task 7 marks the upload `FAILED` with a "try again" message if queueing raises |
| Neon pauses its database when idle, so the first query is slow or a stale pooled connection fails | Med | `pool_pre_ping=True` and a short `pool_recycle` on Postgres engines (Task 1) |
| Firebase Hosting's 60-second timeout cuts off sync for very large schedules | Low | Sync is safe to re-run, so pressing Sync again finishes it. Listed under known limitations (Task 12); moving sync onto the queue is future work. |
| Windows and the slim Linux image have no timezone database, so `ZoneInfo` raises | Med | Add the `tzdata` package (Task 4) |
| Free tiers change, or traffic grows past them | Low | Budget alert at $5 (Task 9); Cloud Run `max-instances` capped |
| `*.web.app` can't be used as the verified homepage for Google verification | Low now, blocks going public | Check Google's requirements during Task 9. A custom domain is the fallback, at about $12 a year. |

## Resolved Questions

1. **Local Postgres:** Docker (`postgres:16`), the same image CI uses. Docker Desktop has to be
   installed first (prerequisite in Task 1).
2. **Worker topology:** one service, with the token checked in the app (decision 4).
3. **Timezone source:** the browser's timezone, sent on each sync (decision 8).

## Open Questions

1. **Does a `*.web.app` address satisfy Google verification?** Answer during Task 9, before
   asking friends to use it.
