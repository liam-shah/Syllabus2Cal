"""Sign-in routes: /auth/google/login and /callback, POST /auth/sign-out, GET /auth/status.

/login and /callback are *page navigations* (the browser goes there), not API calls, so
they answer with redirects - back to the frontend - rather than JSON.
"""

from enum import StrEnum
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from app import session_cookie
from app.config import settings
from app.dependencies import get_auth_service, get_optional_user
from app.integrations import google_sign_in
from app.models import User
from app.schemas import AuthStatusOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class SignInOutcome(StrEnum):
    """Where a successful sign-in left the calendar connection. Sent to the frontend."""

    CONNECTED = "connected"      # signed in, and Google Calendar is connected
    NO_CALENDAR = "no_calendar"  # signed in, but there's no calendar access to sync with yet


class SignInFailure(StrEnum):
    """Why sign-in failed. Sent to the frontend as a fixed code, never as raw error text."""

    ACCESS_DENIED = "access_denied"       # the user clicked Cancel on Google's screen
    GOOGLE_ERROR = "google_error"         # Google reported some other problem
    INVALID_STATE = "invalid_state"       # not started in this browser, expired, or reused
    EXCHANGE_FAILED = "exchange_failed"   # Google rejected the code, or its ID token didn't check out


def redirect_to_frontend(**query: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/?{urlencode(query)}")


@router.get("/google/login")
def google_login(request: Request, connect_calendar: bool = False):
    url, state, code_verifier = google_sign_in.get_authorization_url(ask_for_consent=connect_calendar)
    session_cookie.start_login_attempt(request, state, code_verifier)
    return RedirectResponse(url)


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth: AuthService = Depends(get_auth_service),
):
    # Read (and remove) the attempt before anything else, so a failed sign-in can't be retried.
    code_verifier = session_cookie.finish_login_attempt(request, state)

    if error:
        reason = SignInFailure.ACCESS_DENIED if error == "access_denied" else SignInFailure.GOOGLE_ERROR
        return redirect_to_frontend(google="error", reason=reason)
    if code is None or code_verifier is None:
        return redirect_to_frontend(google="error", reason=SignInFailure.INVALID_STATE)

    try:
        google = google_sign_in.complete_sign_in(code, code_verifier)
    except google_sign_in.GoogleSignInError:
        # The one place a router catches an AppError itself: a page navigation should end on
        # a page, not on a JSON error from the central handler.
        return redirect_to_frontend(google="error", reason=SignInFailure.EXCHANGE_FAILED)

    # Signing in as someone (else) ends whatever session this browser had before.
    previous_token = session_cookie.read_token(request)
    if previous_token is not None:
        auth.sign_out(previous_token)

    user, token = auth.sign_in(google)
    session_cookie.start_session(request, token)
    outcome = SignInOutcome.CONNECTED if user.is_calendar_connected else SignInOutcome.NO_CALENDAR
    return redirect_to_frontend(google=outcome)


# POST, not GET: browsers send cookies with cross-site GET links (SameSite=Lax), so any other
# site could sign people out with a link to a GET route.
@router.post("/sign-out", status_code=204)
def sign_out(request: Request, auth: AuthService = Depends(get_auth_service)):
    token = session_cookie.read_token(request)
    if token is not None:
        auth.sign_out(token)
    session_cookie.end_session(request)
    return Response(status_code=204)


@router.get("/status", response_model=AuthStatusOut)
def auth_status(user: User | None = Depends(get_optional_user)):
    # Answers for signed-out visitors too (rather than a 401), since "not signed in" is the
    # normal answer the frontend asks this route for.
    if user is None:
        return AuthStatusOut(signed_in=False)
    return AuthStatusOut(signed_in=True, email=user.email, calendar_connected=user.is_calendar_connected)
