"""Signing in and out through the real app: cookies, redirects, and which routes need a session.

Only Google is faked. The test client keeps cookies between requests like a browser, so
these tests sign in the same way a person does.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.integrations.google_sign_in import GoogleSignIn, GoogleSignInError
from app.main import app
from app.models import LoginSession
from app.session_cookie import COOKIE_NAME

GOOGLE_URL = "https://accounts.google.com/o/oauth2/auth?x=1"
ALICE = GoogleSignIn(subject="google-alice", email="alice@example.com", calendar_credentials_json='{"token": "alice"}')
BOB = GoogleSignIn(subject="google-bob", email="bob@example.com", calendar_credentials_json=None)


def frontend(query: str) -> str:
    return f"{settings.frontend_url}/?{query}"


def start_login(browser: TestClient, state: str = "state-123", connect_calendar: bool = False):
    fake = (GOOGLE_URL, state, f"verifier-for-{state}")
    with patch("app.integrations.google_sign_in.get_authorization_url", return_value=fake) as mock:
        params = {"connect_calendar": "true"} if connect_calendar else {}
        response = browser.get("/auth/google/login", params=params, follow_redirects=False)
    return response, mock


def callback(browser: TestClient, google: GoogleSignIn | Exception = ALICE, **params):
    """Google sending the user back. `google` is what finishing the sign-in returns (or raises)."""
    side_effect = google if isinstance(google, Exception) else None
    with patch("app.integrations.google_sign_in.complete_sign_in",
               return_value=google, side_effect=side_effect) as mock:
        response = browser.get("/auth/google/callback", params=params, follow_redirects=False)
    return response, mock


def sign_in(browser: TestClient, google: GoogleSignIn = ALICE):
    start_login(browser)
    response, _ = callback(browser, google, code="code-xyz", state="state-123")
    return response


def status(browser: TestClient) -> dict:
    return browser.get("/auth/status").json()


@pytest.fixture
def browser(signed_out_client) -> TestClient:
    return signed_out_client


@pytest.fixture
def other_browser(browser) -> TestClient:
    # Same app and database (the overrides are app-wide), but its own cookie jar.
    return TestClient(app)


# --- Signing in ----------------------------------------------------------------------------

def test_login_sends_the_browser_to_google(browser):
    response, mock = start_login(browser)

    assert response.status_code == 307
    assert response.headers["location"] == GOOGLE_URL
    mock.assert_called_once_with(ask_for_consent=False)


def test_connecting_the_calendar_asks_google_for_consent(browser):
    _, mock = start_login(browser, connect_calendar=True)
    mock.assert_called_once_with(ask_for_consent=True)


def test_signing_in_starts_a_session(browser):
    response = sign_in(browser)

    assert response.headers["location"] == frontend("google=connected")
    assert status(browser) == {"signed_in": True, "email": "alice@example.com", "calendar_connected": True}


def test_the_callback_gets_the_code_verifier_saved_when_login_started(browser):
    start_login(browser)
    _, mock = callback(browser, code="code-xyz", state="state-123")
    mock.assert_called_once_with("code-xyz", "verifier-for-state-123")


def test_signing_in_without_calendar_access_says_so(browser):
    assert sign_in(browser, BOB).headers["location"] == frontend("google=no_calendar")
    assert status(browser) == {"signed_in": True, "email": "bob@example.com", "calendar_connected": False}


def test_the_session_cookie_is_locked_down(browser):
    response = sign_in(browser)
    cookie = response.headers["set-cookie"].lower()

    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "httponly" in cookie   # page JavaScript can't read it
    assert "samesite=lax" in cookie
    assert "secure" not in cookie  # local development is plain http; deployed (https) adds it


def test_a_sign_in_finished_in_a_different_browser_is_refused(browser, other_browser):
    # Login CSRF: an attacker starts a sign-in to *their* account, then tricks someone into
    # opening the callback link. Without the attempt in this browser's cookie, it's refused.
    start_login(browser)
    response, mock = callback(other_browser, code="code-xyz", state="state-123")

    assert response.headers["location"] == frontend("google=error&reason=invalid_state")
    mock.assert_not_called()
    assert status(other_browser) == {"signed_in": False, "email": None, "calendar_connected": False}


def test_each_sign_in_link_only_works_once(browser):
    sign_in(browser)
    reused, _ = callback(browser, code="code-xyz", state="state-123")
    assert reused.headers["location"] == frontend("google=error&reason=invalid_state")


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"error": "access_denied"}, "access_denied"),         # user clicked Cancel
        ({"error": "server_error"}, "google_error"),           # any other Google error
        ({"code": "code-xyz", "state": "wrong-state"}, "invalid_state"),
        ({"state": "state-123"}, "invalid_state"),             # no code at all
    ],
)
def test_failed_sign_ins_return_to_the_app_with_a_reason(browser, params, reason):
    start_login(browser)
    response, _ = callback(browser, **params)

    assert response.status_code == 307
    assert response.headers["location"] == frontend(f"google=error&reason={reason}")
    assert status(browser)["signed_in"] is False


def test_a_sign_in_google_rejects_returns_to_the_app(browser):
    start_login(browser)
    response, _ = callback(browser, GoogleSignInError("invalid_grant"), code="code-xyz", state="state-123")
    assert response.headers["location"] == frontend("google=error&reason=exchange_failed")


def test_cancelling_a_reconnect_keeps_you_signed_in(browser):
    sign_in(browser)
    start_login(browser, state="state-456", connect_calendar=True)
    callback(browser, error="access_denied", state="state-456")

    assert status(browser)["signed_in"] is True


def test_signing_in_as_someone_else_ends_the_previous_session(browser, db):
    sign_in(browser, ALICE)
    sign_in(browser, BOB)

    assert status(browser)["email"] == "bob@example.com"
    assert len(db.scalars(select(LoginSession)).all()) == 1  # Alice's session was deleted


# --- Signing out ---------------------------------------------------------------------------

def test_signing_out_ends_the_session(browser):
    sign_in(browser)
    response = browser.post("/auth/sign-out")

    assert response.status_code == 204
    assert status(browser)["signed_in"] is False


def test_a_copied_cookie_stops_working_after_signing_out(browser, other_browser):
    # The point of keeping sessions in the database: a stolen cookie can be revoked.
    sign_in(browser)
    other_browser.cookies.set(COOKIE_NAME, browser.cookies[COOKIE_NAME])
    assert status(other_browser)["signed_in"] is True

    browser.post("/auth/sign-out")

    assert status(other_browser)["signed_in"] is False


def test_signing_out_when_not_signed_in_is_harmless(browser):
    assert browser.post("/auth/sign-out").status_code == 204


def test_a_tampered_cookie_counts_as_signed_out(browser):
    browser.cookies.set(COOKIE_NAME, "eyJ0b2tlbiI6ICJndWVzcyJ9.forged.signature")
    assert status(browser)["signed_in"] is False


# --- Which routes need a session -----------------------------------------------------------

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/uploads"),
        ("get", "/uploads/1"),
        ("get", "/events/preview?upload_id=1"),
        ("patch", "/events/1"),
        ("post", "/events/sync?upload_id=1"),
    ],
)
def test_every_data_route_needs_a_session(browser, method, path):
    response = browser.request(method, path)
    assert response.status_code == 401
    assert "Sign in with Google" in response.json()["detail"]


def test_a_signed_in_browser_gets_through(browser):
    sign_in(browser)
    assert browser.get("/uploads/999").status_code == 404  # past the sign-in check
