"""Checking that a request really comes from our Cloud Tasks queue. Google's signature check is
faked: it's Google's library's job, and testing it would need Google's private keys."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic import ValidationError

from app.config import Settings
from app.integrations.cloud_tasks import QueueError, TaskTokenError, enqueue_extraction, verify_task_token

SERVICE_URL = "https://api-abc123-uw.a.run.app"
TASKS_ACCOUNT = "tasks@syllabus2cal.iam.gserviceaccount.com"


def google_says(claims=None, raises: Exception | None = None):
    """Replace Google's signature + audience + expiry check with a fixed answer."""
    target = "app.integrations.cloud_tasks.id_token.verify_oauth2_token"
    return patch(target, side_effect=raises) if raises else patch(target, return_value=claims)


def verify(token: str = "signed-token") -> None:
    verify_task_token(token, audience=SERVICE_URL, service_account=TASKS_ACCOUNT)


def test_a_token_from_the_tasks_account_for_this_service_is_accepted():
    with google_says({"email": TASKS_ACCOUNT, "email_verified": True}) as check:
        verify()
    # Google's library is asked to check that the token was issued for *this* service.
    assert check.call_args.kwargs["audience"] == SERVICE_URL


def test_a_token_google_rejects_is_refused():
    # Bad signature, expired, or issued for another audience (another service's URL).
    with google_says(raises=ValueError("Token has wrong audience")), pytest.raises(TaskTokenError):
        verify()


def test_a_genuine_google_token_from_another_account_is_refused():
    # Anyone can get a Google-signed token for their own account with our URL as audience.
    with google_says({"email": "someone@gmail.com", "email_verified": True}), pytest.raises(TaskTokenError):
        verify()


def test_an_unverified_email_is_refused():
    with google_says({"email": TASKS_ACCOUNT, "email_verified": False}), pytest.raises(TaskTokenError):
        verify()


def test_a_refusal_is_a_401():
    from app.main import status_code_for

    assert status_code_for(TaskTokenError("not from Cloud Tasks")) == 401


# --- Queueing an extraction ------------------------------------------------------------------

QUEUE = "projects/syllabus2cal/locations/us-west1/queues/extractions"


def google_api_answers(status: int = 200, text: str = "{}"):
    """Fake the service's own Google credentials and the HTTP call made with them."""
    session = MagicMock()
    session.post.return_value = MagicMock(ok=200 <= status < 300, status_code=status, text=text)
    return (patch("app.integrations.cloud_tasks.google.auth.default", return_value=(MagicMock(), "syllabus2cal")),
            patch("app.integrations.cloud_tasks.AuthorizedSession", return_value=session), session)


def enqueue(upload_id: int = 42) -> None:
    enqueue_extraction(upload_id, queue=QUEUE, service_url=SERVICE_URL, service_account=TASKS_ACCOUNT)


def test_queueing_creates_a_task_that_calls_this_service_with_the_tasks_accounts_token():
    credentials, authorized_session, session = google_api_answers()
    with credentials, authorized_session:
        enqueue(42)

    url = session.post.call_args.args[0]
    request = session.post.call_args.kwargs["json"]["task"]["httpRequest"]
    assert url == f"https://cloudtasks.googleapis.com/v2/{QUEUE}/tasks"
    # Straight to run.app, not through Firebase (whose 60-second limit would cut Claude off).
    assert request["url"] == f"{SERVICE_URL}/internal/extractions/42"
    assert request["httpMethod"] == "POST"
    assert "body" not in request  # the upload id in the URL is all the job needs
    # What verify_task_token checks on the way back in.
    assert request["oidcToken"] == {"serviceAccountEmail": TASKS_ACCOUNT, "audience": SERVICE_URL}


def test_google_refusing_the_task_is_a_queue_error():
    credentials, authorized_session, _ = google_api_answers(status=403, text="Permission denied on queue")
    with credentials, authorized_session, pytest.raises(QueueError, match="403"):
        enqueue()


def test_a_half_configured_queue_stops_the_app_starting():
    # Otherwise uploads would quietly fall back to BackgroundTasks, which Cloud Run starves of CPU.
    with pytest.raises(ValidationError, match="SERVICE_URL"):
        Settings(_env_file=None, cloud_tasks_queue=QUEUE, tasks_service_account=TASKS_ACCOUNT)
    with pytest.raises(ValidationError, match="TASKS_SERVICE_ACCOUNT"):
        Settings(_env_file=None, cloud_tasks_queue=QUEUE, service_url=SERVICE_URL)
    Settings(_env_file=None, cloud_tasks_queue=QUEUE, service_url=SERVICE_URL, tasks_service_account=TASKS_ACCOUNT)


def test_not_reaching_google_is_a_queue_error():
    credentials, authorized_session, session = google_api_answers()
    session.post.side_effect = requests.ConnectionError("no route to host")
    with credentials, authorized_session, pytest.raises(QueueError):
        enqueue()
