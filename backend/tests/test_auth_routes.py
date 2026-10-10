from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.config import settings
from app.integrations.google_calendar import GoogleCalendarError
from app.models import User
from app.routers import auth


@pytest.fixture(autouse=True)
def no_leftover_sign_in_attempts():
    auth.pending_logins.clear()
    yield
    auth.pending_logins.clear()


def frontend(query: str) -> str:
    return f"{settings.frontend_url}/?{query}"


def callback(client, **params):
    return client.get("/auth/google/callback", params=params, follow_redirects=False)


def test_login_redirects_to_google_and_remembers_the_attempt(client):
    # Patched so the test doesn't need the real client_secret.json (not in the repo).
    fake_url = ("https://accounts.google.com/o/oauth2/auth?x=1", "state-123", "verifier-abc")
    with patch("app.integrations.google_calendar.get_authorization_url", return_value=fake_url):
        response = client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == fake_url[0]
    assert auth.pending_logins == {"state-123": "verifier-abc"}


def test_successful_sign_in_saves_credentials_and_returns_to_the_app(client, db):
    auth.pending_logins["state-123"] = "verifier-abc"
    fake_credentials = MagicMock()
    fake_credentials.to_json.return_value = '{"token": "fake"}'

    with patch("app.integrations.google_calendar.exchange_code_for_credentials",
               return_value=fake_credentials) as mock_exchange:
        response = callback(client, code="code-xyz", state="state-123")

    assert response.headers["location"] == frontend("google=connected")
    mock_exchange.assert_called_once_with("code-xyz", "verifier-abc")
    assert db.scalars(select(User)).one().google_credentials_json == '{"token": "fake"}'
    assert client.get("/auth/google/status").json() == {"connected": True}


def test_each_sign_in_link_only_works_once(client):
    auth.pending_logins["state-123"] = "verifier-abc"
    fake_credentials = MagicMock()
    fake_credentials.to_json.return_value = '{"token": "fake"}'

    with patch("app.integrations.google_calendar.exchange_code_for_credentials",
               return_value=fake_credentials):
        first = callback(client, code="code-xyz", state="state-123")
        reused = callback(client, code="code-xyz", state="state-123")

    assert first.headers["location"] == frontend("google=connected")
    assert reused.headers["location"] == frontend("google=error&reason=invalid_state")


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"error": "access_denied"}, "access_denied"),         # user clicked Cancel
        ({"error": "server_error"}, "google_error"),           # any other Google error
        ({"code": "code-xyz", "state": "never-issued"}, "invalid_state"),
        ({"state": "state-123"}, "invalid_state"),             # no code at all
    ],
)
def test_failed_sign_ins_return_to_the_app_with_a_reason(client, params, reason):
    auth.pending_logins["state-123"] = "verifier-abc"
    response = callback(client, **params)
    assert response.status_code == 307
    assert response.headers["location"] == frontend(f"google=error&reason={reason}")


def test_rejected_code_exchange_returns_to_the_app(client):
    auth.pending_logins["state-123"] = "verifier-abc"
    with patch("app.integrations.google_calendar.exchange_code_for_credentials",
               side_effect=GoogleCalendarError("invalid_grant")):
        response = callback(client, code="code-xyz", state="state-123")

    assert response.headers["location"] == frontend("google=error&reason=exchange_failed")


def test_status_is_not_connected_before_signing_in(client):
    assert client.get("/auth/google/status").json() == {"connected": False}
