# 1. Use Neon Postgres for the deployed database

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Locally the app uses a SQLite file (`backend/app.db`). The deployed backend runs on Cloud
Run, which doesn't keep files on disk: anything written to it is lost when an instance
stops, and every instance has its own copy. So SQLite can't be the deployed database. I
want the beta to cost about $0 a month apart from Claude calls, and I'd rather not rewrite
the data layer. That layer is SQLAlchemy models, Alembic migrations, CHECK constraints on
the status columns, and compare-and-set `UPDATE ... WHERE` statements.

## Decision

Use **Postgres on Neon's free tier**, in AWS us-west-2 (Oregon), next to Cloud Run in
us-west1.

- The only code change is the driver (`psycopg[binary]`) and one engine option.
- `pool_pre_ping=True` is set for Postgres. Neon suspends an idle database and drops its
  connections, so each pooled connection is checked (one cheap round trip) before use
  instead of failing the request.
- The backend suite runs against Postgres when `TEST_DATABASE_URL` is set. Locally that's a
  `postgres:16` Docker container; in CI it's a service container.

## Alternatives considered

| Option | Why not |
|---|---|
| Cloud SQL for Postgres | Same database, and it would keep everything inside Google Cloud, but the smallest instance costs about $10 a month even when idle. |
| Firestore | Already part of Firebase and has a free tier, but it would mean rewriting the models, migrations, constraints and compare-and-set logic: the most interesting part of the codebase, for no gain users would see. |
| SQLite + Litestream on Cloud Run | $0 and no database change, but it needs a single instance and a restore step at startup. Fragile, and not something I'd open to the public. |

## Consequences

- **Verified:** all 4 existing migrations run on an empty Postgres database, and the CHECK
  constraint on `uploads.status` is replaced correctly rather than dropped. A new test
  checks this on both databases. All 153 backend tests pass on SQLite and on Postgres.
- The first request after Neon has been idle is slower while the database wakes up.
- A new dependency on an outside provider. If Neon's free tier changes, the move is to
  another Postgres host (or Cloud SQL) with a new `DATABASE_URL`. No code changes.
- Tests that pass on SQLite but fail on Postgres are now possible, so CI must run both.
