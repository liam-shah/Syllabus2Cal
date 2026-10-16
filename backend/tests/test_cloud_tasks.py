"""Checking that a request really comes from our Cloud Tasks queue. Google's signature check is
faked: it's Google's library's job, and testing it would need Google's private keys."""

from unittest.mock import patch

import pytest

from app.integrations.cloud_tasks import TaskTokenError, verify_task_token

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
