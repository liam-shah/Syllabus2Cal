"""Cloud Tasks: queueing an extraction, and checking that a request to the worker route
really comes from our queue.

The worker route is on the same public Cloud Run service as the rest of the API, so anyone
can call it. Cloud Tasks attaches a Google-signed ID token (OIDC) for the tasks service
account, with this service's URL as its audience; only a token like that is accepted.
"""

import google.auth
import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token

from app.errors import ExternalServiceError, NotSignedInError

CLOUD_TASKS_API = "https://cloudtasks.googleapis.com/v2"
# How long the queue waits for the worker route to answer. Matches EXTRACTION_TIMEOUT, after
# which get_upload gives up on an upload anyway; Cloud Run's request timeout must be at least this.
DISPATCH_DEADLINE = "900s"


class TaskTokenError(NotSignedInError):
    """The request isn't from our Cloud Tasks queue (-> 401)."""


class QueueError(ExternalServiceError):
    """Cloud Tasks didn't accept the task (-> 502)."""


def enqueue_extraction(upload_id: int, queue: str, service_url: str, service_account: str) -> None:
    """Ask Cloud Tasks to POST to this service's worker route for `upload_id`.

    queue: "projects/<project>/locations/<region>/queues/<name>". The task goes to service_url
    (the run.app URL, not Firebase, whose 60-second limit would cut Claude off), carrying a
    token for service_account with service_url as its audience - what verify_task_token expects.
    """
    task = {
        "httpRequest": {
            "httpMethod": "POST",
            "url": f"{service_url}/internal/extractions/{upload_id}",
            "oidcToken": {"serviceAccountEmail": service_account, "audience": service_url},
        },
        "dispatchDeadline": DISPATCH_DEADLINE,
    }
    try:
        # The Cloud Run service's own identity (or your gcloud login, locally).
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        response = AuthorizedSession(credentials).post(f"{CLOUD_TASKS_API}/{queue}/tasks", json={"task": task}, timeout=10)
    except (GoogleAuthError, requests.RequestException) as e:
        raise QueueError(f"Couldn't reach Cloud Tasks: {e}") from e
    if not response.ok:
        raise QueueError(f"Cloud Tasks refused the task ({response.status_code}: {response.text[:200]})")


def verify_task_token(token: str, audience: str, service_account: str) -> None:
    """Raise TaskTokenError unless `token` is a Google-signed token for `service_account`,
    issued for `audience` (this service's own URL)."""
    try:
        # Checks Google's signature, that the token hasn't expired, and the audience: a token
        # minted for some other service can't be replayed here. Fetches Google's public keys.
        claims = id_token.verify_oauth2_token(token, Request(), audience=audience)
    except ValueError as e:
        # A fixed message: the reason (bad signature, wrong audience...) is no business of the caller's.
        raise TaskTokenError("This request isn't from the extraction queue.") from e

    # Anyone can get a Google-signed token for *their own* account with our URL as audience,
    # so the signature alone proves nothing - it has to be the tasks account's.
    if claims.get("email") != service_account or not claims.get("email_verified"):
        raise TaskTokenError("This request isn't from the extraction queue.")
