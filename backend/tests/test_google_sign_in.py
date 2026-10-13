"""google_sign_in: what we trust from Google's answer, and what we refuse.

Google's servers are faked: the OAuth Flow and the ID token check are patched.
"""

from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError

from app.integrations import google_sign_in
from app.integrations.google_calendar import CALENDAR_SCOPE, has_calendar_access
from app.integrations.google_sign_in import GoogleSignInError, complete_sign_in, get_authorization_url

CLAIMS = {"sub": "google-123", "email": "a@example.com", "email_verified": True}


def credentials(scopes=("openid", CALENDAR_SCOPE), refresh_token="refresh", id_token="id-token") -> Credentials:
    creds = Credentials(token="access", refresh_token=refresh_token, granted_scopes=list(scopes))
    creds._id_token = id_token  # set by google-auth after a real token exchange
    return creds


def fake_flow(creds: Credentials | None = None, fetch_error: Exception | None = None) -> MagicMock:
    flow = MagicMock()
    flow.credentials = creds or credentials()
    flow.client_config = {"client_id": "our-client-id"}
    flow.fetch_token.side_effect = fetch_error
    flow.authorization_url.return_value = ("https://accounts.google.com/...", "state-1")
    flow.code_verifier = "verifier-1"
    return flow


@pytest.fixture
def verify():
    """Google's ID token check, answering with CLAIMS unless a test says otherwise."""
    with patch.object(google_sign_in.id_token, "verify_oauth2_token", return_value=CLAIMS) as mock:
        yield mock


def sign_in_with(flow: MagicMock):
    with patch.object(google_sign_in, "build_flow", return_value=flow):
        return complete_sign_in("code", "verifier")


@pytest.mark.parametrize(("ask_for_consent", "prompt"), [(False, "select_account"), (True, "consent")])
def test_only_reconnecting_shows_the_consent_screen(ask_for_consent, prompt):
    flow = fake_flow()
    with patch.object(google_sign_in, "build_flow", return_value=flow):
        assert get_authorization_url(ask_for_consent) == ("https://accounts.google.com/...", "state-1", "verifier-1")
    assert flow.authorization_url.call_args.kwargs["prompt"] == prompt


def test_a_good_sign_in_says_who_it_is_and_brings_calendar_access(verify):
    result = sign_in_with(fake_flow())

    assert (result.subject, result.email) == ("google-123", "a@example.com")
    assert result.calendar_credentials_json is not None
    # The ID token must have been issued to *our* app, not to some other site.
    assert verify.call_args.kwargs["audience"] == "our-client-id"


def test_a_rejected_code_is_a_sign_in_error(verify):
    with pytest.raises(GoogleSignInError):
        sign_in_with(fake_flow(fetch_error=InvalidGrantError()))


def test_no_id_token_is_refused(verify):
    with pytest.raises(GoogleSignInError, match="no ID token"):
        sign_in_with(fake_flow(credentials(id_token=None)))


def test_an_id_token_that_fails_the_check_is_refused(verify):
    verify.side_effect = ValueError("Token has wrong audience")
    with pytest.raises(GoogleSignInError, match="didn't check out"):
        sign_in_with(fake_flow())


def test_an_unverified_email_is_refused(verify):
    verify.return_value = CLAIMS | {"email_verified": False}
    with pytest.raises(GoogleSignInError, match="isn't verified"):
        sign_in_with(fake_flow())


def test_unticking_the_calendar_permission_still_signs_in_but_without_calendar_access(verify):
    result = sign_in_with(fake_flow(credentials(scopes=("openid",))))
    assert result.subject == "google-123"
    assert result.calendar_credentials_json is None


@pytest.mark.parametrize(
    ("creds", "expected"),
    [
        (credentials(), True),
        (credentials(scopes=("openid",)), False),     # calendar permission unticked
        (credentials(refresh_token=None), False),     # access would expire within the hour
    ],
)
def test_calendar_access_needs_the_permission_and_a_refresh_token(creds, expected):
    assert has_calendar_access(creds) is expected
