# Deploying Syllabus2Cal

A copy-paste runbook for the first deploy. Each part runs once, in order, from the repo root in
**Git Bash**. Task 11 later automates parts 6–8 in GitHub Actions; the rest is one-time setup.

What ends up running:

```
Browser ──> Firebase Hosting (<project>.web.app)
              ├─ static frontend (frontend/dist)
              └─ /api/** ──> Cloud Run service "api" (us-west1) ──> Neon Postgres (aws us-west-2)
Cloud Tasks queue "extractions" ──> https://api-<project number>.us-west1.run.app/internal/extractions/<id>
```

Why it's shaped like this: [ADR 1](adr/0001-neon-postgres.md) (database), [ADR 2](adr/0002-extraction-job-contract.md)
(extraction job), [ADR 3](adr/0003-worker-endpoint-auth.md) (worker route auth),
[ADR 4](adr/0004-same-origin-api.md) (same-origin `/api`).

> **No secret ever goes in the repo or the image.** Secrets live in Secret Manager. The commands
> below read them from your shell or a local file; don't paste real values into this document.

---

## 0. Tools

- [gcloud CLI](https://cloud.google.com/sdk/docs/install), then `gcloud auth login`
- Firebase CLI: `npm install -g firebase-tools`, then `firebase login`
- Docker Desktop. **Start it from the Start menu (or through Explorer), not from a terminal inside
  the Claude desktop app.** That app sandboxes Docker's files, and a crash then stops Docker
  starting again.

Set these once per terminal session. Every later command uses them.

```bash
PROJECT_ID=your-project-id          # the Google Cloud / Firebase project
REGION=us-west1
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SERVICE_URL="https://api-$PROJECT_NUMBER.$REGION.run.app"   # Cloud Run's deterministic URL
SITE_URL="https://$PROJECT_ID.web.app"
RUNTIME_SA="api-runtime@$PROJECT_ID.iam.gserviceaccount.com"
TASKS_SA="tasks-invoker@$PROJECT_ID.iam.gserviceaccount.com"
QUEUE="projects/$PROJECT_ID/locations/$REGION/queues/extractions"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/syllabus2cal/api:$(git rev-parse --short HEAD)"
gcloud config set project "$PROJECT_ID"
```

---

## 1. Project, billing and a budget alert

1. **Use the Google Cloud project that already has your OAuth client** (the one in
   `backend/client_secret.json`, with the Calendar API enabled). In the
   [Firebase console](https://console.firebase.google.com) choose *Add project → Add Firebase to a
   Google Cloud project* and pick it. That keeps sign-in, the Calendar API, Cloud Run and Hosting
   in one project.
2. Switch the Firebase project to the **Blaze** (pay-as-you-go) plan. Forwarding Hosting to Cloud
   Run requires it, as do Cloud Run and Cloud Tasks. At beta traffic everything here stays within
   the free tiers. Claude calls are billed separately, by Anthropic.
3. Add a **$5 budget alert**: *Billing → Budgets & alerts → Create budget*, $5, alerts at 50%,
   90% and 100%. An alert doesn't stop spending; it emails you.

## 2. Turn on the APIs

```bash
gcloud services enable run.googleapis.com cloudtasks.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com calendar-json.googleapis.com
```

## 3. Database (Neon)

1. Create a [Neon](https://neon.tech) project in **AWS us-west-2 (Oregon)**, next to Cloud Run.
2. Copy the **direct** connection string, not the `-pooler` one. The app keeps its own small
   connection pool, and the pooler's transaction mode doesn't mix well with psycopg's prepared
   statements.
3. Turn it into the app's format by swapping the scheme to `postgresql+psycopg://`:

   ```bash
   DATABASE_URL='postgresql+psycopg://USER:PASSWORD@ep-xxxx.us-west-2.aws.neon.tech/neondb?sslmode=require'
   ```

4. Create the tables (from `backend/`, with the venv active; `.env` supplies the other settings):

   ```bash
   (cd backend && DATABASE_URL="$DATABASE_URL" alembic upgrade head)
   ```

## 4. Secrets

```bash
# Stop here if either is unset: piping an empty variable would create an empty secret.
: "${ANTHROPIC_API_KEY:?export your Anthropic API key first}" "${DATABASE_URL:?set DATABASE_URL (part 3) first}"
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-
python -c "import secrets; print(secrets.token_urlsafe(32), end='')" | gcloud secrets create session-secret-key --data-file=-
printf '%s' "$DATABASE_URL" | gcloud secrets create database-url --data-file=-
gcloud secrets create google-client-secret --data-file=backend/client_secret.json
```

The session secret is generated fresh for production; never reuse your local one. Changing it
later signs everyone out.

## 5. Service accounts, the queue and the image registry

```bash
# Who the API runs as, and the identity every Cloud Task's token is issued for.
gcloud iam service-accounts create api-runtime --display-name="Syllabus2Cal API"
gcloud iam service-accounts create tasks-invoker --display-name="Syllabus2Cal Cloud Tasks"

# The API reads its four secrets...
for s in anthropic-api-key session-secret-key database-url google-client-secret; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
done

# ...queues extraction tasks (at most 3 attempts; the worker route makes retries free, see ADR 2)...
gcloud tasks queues create extractions --location="$REGION" --max-attempts=3 --max-concurrent-dispatches=5
gcloud tasks queues add-iam-policy-binding extractions --location="$REGION" \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/cloudtasks.enqueuer

# ...and may create tasks that carry the tasks account's token.
gcloud iam service-accounts add-iam-policy-binding "$TASKS_SA" \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/iam.serviceAccountUser
```

The tasks account needs no roles of its own: the service is public, and the app checks the
token itself ([ADR 3](adr/0003-worker-endpoint-auth.md)). Only for a project created **before
March 2019**, also run
`gcloud iam service-accounts add-iam-policy-binding "$TASKS_SA" --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-cloudtasks.iam.gserviceaccount.com" --role=roles/iam.serviceAccountTokenCreator`.

Image registry. Each image is ~560 MB unpacked, and Artifact Registry's free tier is 0.5 GB, so
keep only the newest two:

```bash
gcloud artifacts repositories create syllabus2cal --repository-format=docker --location="$REGION"
cat > /tmp/cleanup.json <<'EOF'
[
  {"name": "keep-newest", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "delete-rest", "action": {"type": "Delete"}, "condition": {"tagState": "any"}}
]
EOF
# --no-dry-run: without it, cleanup policies only report what they would delete.
gcloud artifacts repositories set-cleanup-policies syllabus2cal --location="$REGION" --policy=/tmp/cleanup.json --no-dry-run
gcloud auth configure-docker "$REGION-docker.pkg.dev"
```

## 6. Build and push the backend image

```bash
docker build -t "$IMAGE" backend
docker push "$IMAGE"
```

## 7. Deploy the API to Cloud Run

```bash
gcloud run deploy api --image="$IMAGE" --region="$REGION" --service-account="$RUNTIME_SA" \
  --allow-unauthenticated --max-instances=2 --concurrency=20 --timeout=900 --memory=1Gi \
  --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,SESSION_SECRET_KEY=session-secret-key:latest,DATABASE_URL=database-url:latest,/secrets/google/client_secret.json=google-client-secret:latest" \
  --set-env-vars="GOOGLE_CLIENT_SECRET_PATH=/secrets/google/client_secret.json,FRONTEND_URL=$SITE_URL,BACKEND_URL=$SITE_URL/api,CLOUD_TASKS_QUEUE=$QUEUE,SERVICE_URL=$SERVICE_URL,TASKS_SERVICE_ACCOUNT=$TASKS_SA"

# The URL Cloud Tasks will call must be the one the app expects as its token audience:
gcloud run services describe api --region="$REGION" --format='value(status.url)'   # should print $SERVICE_URL
```

What the flags are for:

| Flag | Why |
|---|---|
| `--allow-unauthenticated` | Browsers reach it through Firebase. Every data route checks the session, and the worker route checks the Cloud Tasks token. |
| `--timeout=900` | The worker route waits for Claude. It matches the queue's 15-minute dispatch deadline and the app's give-up timeout. |
| `--concurrency=20` | Each extraction holds a server thread for about a minute, so keep plenty free for normal requests. |
| `--max-instances=2` | Caps cost if something loops. |
| `--memory=1Gi` | Room for pdfplumber on a 10 MB PDF. |
| `BACKEND_URL=$SITE_URL/api` | The Google sign-in redirect URI is built from it, and it's HTTPS, so cookies are `Secure`. |

If the deploy fails with *"CLOUD_TASKS_QUEUE is set, so these are needed too"*, a variable from
part 0 is empty in this shell.

## 8. Deploy the frontend to Firebase Hosting

```bash
firebase use --add "$PROJECT_ID"        # once: writes .firebaserc (commit it)
(cd frontend && npm ci && npm run build) # uses frontend/.env.production: VITE_API_URL=/api
firebase deploy --only hosting
```

## 9. Google sign-in for the live URL

In [Google Cloud console → Google Auth Platform](https://console.cloud.google.com/auth):

1. **Clients** → your web client → *Authorized redirect URIs* → add
   `https://<project-id>.web.app/api/auth/google/callback`. Keep the localhost one for development.
2. **Branding** → *Authorized domains* → add `<project-id>.web.app`.
3. **Audience** → stay in **Testing**. Add each person who may sign in under *Test users* (up to
   100). Their Calendar access expires every 7 days in Testing mode; *Reconnect* in the app renews it.

---

## Smoke test (Checkpoint 3)

On your phone, at `https://<project-id>.web.app`:

- [ ] Sign in, upload a real schedule, review it, sync: the events appear in Google Calendar
- [ ] Redeploy (part 7) while an upload is extracting: it finishes, or fails with a message, and is never stuck
- [ ] Two tabs press Sync at the same time: each event appears once
- [ ] A scanned PDF gets the "no text" message; a second test user can sign in
- [ ] `curl -X POST "$SERVICE_URL/internal/extractions/1"` returns **401**
- [ ] The billing page shows about $0, and the budget alert is listed

If uploads stay "processing": check *Cloud Tasks → extractions* for failed attempts, then
*Cloud Run → api → Logs*. A 401 on the task means `SERVICE_URL` or `TASKS_SERVICE_ACCOUNT`
doesn't match what the queue sends.

## Going public later

The app is technically ready (see `tasks/plan.md`). What's left is Google's verification of the
Calendar permission, which needs a homepage and privacy policy **on a domain you own**. Google
has rejected homepages on platform subdomains you can't prove ownership of, such as GitHub Pages,
and a Firebase `*.web.app` address is at best uncertain. So before submitting: buy a domain
(about $12 a year), connect it in *Firebase Hosting → Custom domain*, verify it in Search
Console, and update `FRONTEND_URL`, `BACKEND_URL` and the OAuth redirect URI to it.
