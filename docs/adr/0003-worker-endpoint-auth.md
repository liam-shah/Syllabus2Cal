# 3. One service, with the worker route checking the Cloud Tasks token itself

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Extraction moves to Cloud Tasks (ADR 2). A task is an HTTP request the queue sends to a URL
of ours, so the app needs a route that runs an extraction. That route mustn't be callable by
anyone else. The damage would be limited, because each processing upload is claimed once
(ADR 2), but it's still an endpoint that triggers paid work.

Cloud Tasks can attach a Google-signed ID token (OIDC) to each task. The token is issued to a
service account we choose, with an audience we choose.

## Decision

**Keep a single Cloud Run service.** Add `POST /internal/extractions/{upload_id}` to it, and
check the token in the app (`integrations/cloud_tasks.py`, run as the router's
`require_cloud_tasks` dependency before any route code):

1. `id_token.verify_oauth2_token` checks Google's signature, the expiry, and that the
   **audience** is this service's own URL (`SERVICE_URL`). A token minted for another service
   can't be replayed here.
2. The token's **email** must be the tasks service account (`TASKS_SERVICE_ACCOUNT`), and
   `email_verified` must be true. This step matters: anyone can get a Google-signed token for
   *their own* account with our URL as the audience, so a valid signature alone proves nothing.

Anything else gets a 401 with a fixed message, before the upload is touched. With the two
settings unset (local development), the route returns 404, and uploads keep using
BackgroundTasks.

The response codes are the retry policy:

| Code | Meaning | Does Cloud Tasks retry? |
|---|---|---|
| 200 | Ran (including when Claude failed and the upload is marked failed) | No |
| 204 | Nothing to do: already claimed, or no longer processing | No |
| 401 | Not from our queue | n/a |
| 500 | Unexpected error: the upload is marked failed | Yes, and the retry gets 204 |

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| A second Cloud Run service (same image) deployed with `--no-allow-unauthenticated`, so Google's platform checks every call | No token code in the app, but twice the deploy, configuration and IAM to manage. The checking code here reuses the library sign-in already uses, and is about 15 lines with a test for every way it can refuse. |
| A shared secret header | A long-lived secret to create, store, rotate and keep out of logs. The OIDC token expires within the hour and is signed by Google. |

## Consequences

- The worker route is on the public internet, so the token check is security-critical code.
  It has tests for:
  - no token
  - the wrong scheme
  - a token Google rejects (bad signature, expired, wrong audience)
  - another account's genuine token
  - an unverified email
  - the real check being wired to the right audience and account
- Cloud Tasks must call the service's `run.app` URL directly, not through Firebase Hosting.
  Firebase's 60-second limit would cut Claude off, and the audience must match `SERVICE_URL`
  exactly.
- Checking a token needs Google's public keys. If fetching them fails, the request errors
  (500) and Cloud Tasks retries it, which is the right outcome for a temporary problem.
- If the worker ever needs isolating (separate scaling, a separate identity), moving to the
  second-service option only changes deploy configuration.
