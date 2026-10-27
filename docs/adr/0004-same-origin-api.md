# 4. Serve the API from the frontend's origin, under /api

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Locally the frontend (port 5173) and backend (port 8000) are different origins. The backend
allows the frontend through CORS, and the browser sends the session cookie with
`credentials: 'include'`. Deployed, the frontend is on Firebase Hosting (`<site>.web.app`)
and the backend on Cloud Run (`<service>.run.app`). Those are different *sites*, not just
different origins, so a `SameSite=Lax` cookie set by `run.app` would be a third-party cookie,
and browsers increasingly block those.

Firebase Hosting can forward a path to a Cloud Run service. It only passes along a cookie
named `__session`, which is why the session cookie already has that name.

## Decision

- Firebase Hosting forwards **`/api/**`** to the Cloud Run service (`firebase.json`). The
  frontend's production build uses **`VITE_API_URL=/api`**, so every request is same-origin
  and the session cookie is first-party. The Google sign-in redirect URI becomes
  `https://<site>.web.app/api/auth/google/callback`.
- **The backend answers every route both at `/api/...` and at its plain path** (the `ApiPrefix`
  middleware in `main.py`). Firebase forwards the path *with* `/api` still on it, but Cloud
  Tasks calls `run.app` directly without it (ADR 3), and so does local development. The
  middleware sets the ASGI `root_path` to `/api` when a request has that prefix, and Starlette
  matches routes on the path after it. Only a whole path segment counts: `/apiauth` and
  `/api/api/...` are still 404s.
- The backend ships as a Docker image (`backend/Dockerfile`): Python 3.13 slim, runtime
  dependencies only (tests live in `requirements-dev.txt`), running as a non-root user.
  `.dockerignore` keeps `.env`, `client_secret.json` and the local databases out of the image.
  Secrets come from the environment (Secret Manager) at runtime.

## Alternatives considered

| Option | Why not |
|---|---|
| `uvicorn --root-path /api` (the plan's first choice) | Tested: uvicorn assumes the proxy has already *removed* the prefix, so `/api/auth/status` from Firebase returned 404. |
| Mount the app under `/api` in a small parent app | Starlette doesn't run a mounted app's lifespan (the startup database check), and Cloud Tasks' unprefixed `/internal/...` path would need a second mount. |
| Prefix every route with `/api` everywhere, locally too | Works, but changes every route test and the local URLs for no gain in production. |
| Call `run.app` from the browser with CORS (like local development) | Cross-site cookies: browsers block or will block them, and Safari already does. |

## Consequences

- CORS stays configured, because local development still uses it, but in production it's unused.
- Requests through Firebase Hosting are cut off after 60 seconds. That's fine for every API
  call except a very large sync (listed as a known limitation). Extraction avoids it by
  running from Cloud Tasks straight to `run.app`.
- The frontend and backend deploy separately but share one URL, so one Firebase site and one
  Cloud Run service (`api`, us-west1) are tied together in `firebase.json`.
