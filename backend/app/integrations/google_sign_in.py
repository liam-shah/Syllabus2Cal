"""Signing in with Google: OAuth 2.0 with PKCE, plus OpenID Connect to learn who the user is.

One trip to Google's sign-in page gives us two separate things:
  - an *ID token*: Google's signed statement of who the person is (used to log them in), and
  - *credentials*: permission to add events to their calendar (used later, for syncing).
"""

import os
from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

from app.config import settings
from app.errors import ExternalServiceError
from app.integrations.google_calendar import CALENDAR_SCOPE, has_calendar_access

# Google's consent screen lets people untick individual permissions, so the scopes granted can
# differ from the ones requested. oauthlib treats that as an error unless this is set; instead,
# complete_sign_in checks what was actually granted.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", CALENDAR_SCOPE]
# Must exactly match an "Authorized redirect URI" on the OAuth client in Google Cloud Console.
REDIRECT_URI = f"{settings.backend_url}/auth/google/callback"


class GoogleSignInError(ExternalServiceError):
    """Google didn't complete the sign-in, or sent back something we can't trust."""


@dataclass(frozen=True)
class GoogleSignIn:
    """The result of a successful sign-in, with no Google library types in it."""

    subject: str  # Google's permanent ID for the account
    email: str
    # Saved credentials for the calendar, or None if this sign-in didn't give lasting access
    # (the calendar box was unticked, or Google skipped the consent screen).
    calendar_credentials_json: str | None


def build_flow(code_verifier: str | None = None) -> Flow:
    return Flow.from_client_secrets_file(
        settings.google_client_secret_path,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        code_verifier=code_verifier,
    )


def get_authorization_url(ask_for_consent: bool) -> tuple[str, str, str]:
    """Google's sign-in page URL, plus the state and PKCE code_verifier to check on the way back.

    ask_for_consent shows the permissions screen even if the user already agreed before - the
    only way to get a new refresh token (needed to connect, or reconnect, the calendar). A
    normal sign-in just asks which account to use.
    """
    flow = build_flow()
    url, state = flow.authorization_url(
        prompt="consent" if ask_for_consent else "select_account",
        include_granted_scopes="true",  # keep permissions granted on earlier sign-ins
    )
    return url, state, flow.code_verifier


def complete_sign_in(code: str, code_verifier: str) -> GoogleSignIn:
    """Swap the one-time code for tokens, then check the ID token before trusting any of it."""
    flow = build_flow(code_verifier=code_verifier)
    try:
        flow.fetch_token(code=code)
    except OAuth2Error as e:
        raise GoogleSignInError(f"Could not finish Google sign-in: {e}") from e
    credentials = flow.credentials

    if not credentials.id_token:
        raise GoogleSignInError("Google didn't say who signed in (no ID token)")
    try:
        # Checks Google's signature, that the token was issued *to this app* (audience),
        # and that it hasn't expired. Fetches Google's public keys to do so.
        claims = id_token.verify_oauth2_token(
            credentials.id_token, Request(), audience=flow.client_config["client_id"]
        )
    except ValueError as e:
        raise GoogleSignInError(f"Google's ID token didn't check out: {e}") from e

    if not claims.get("email_verified"):
        raise GoogleSignInError("This Google account's email address isn't verified")

    return GoogleSignIn(
        subject=claims["sub"],
        email=claims["email"],
        calendar_credentials_json=credentials.to_json() if has_calendar_access(credentials) else None,
    )
