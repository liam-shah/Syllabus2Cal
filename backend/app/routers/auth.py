"""Google sign-in routes: /auth/google/login, /callback, and /status.

/login and /callback are *page navigations* (the browser goes there), not API calls, so
they answer with redirects - back to the frontend - rather than JSON.
"""

from enum import StrEnum
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_current_user
from app.integrations import google_calendar
from app.models import User

router = APIRouter(prefix="/auth/google", tags=["auth"])

# Sign-in attempts only last a few seconds, so keeping them in memory is fine.
pending_logins: dict[str, str] = {}  # state -> code_verifier


class SignInFailure(StrEnum):
    """Why sign-in failed. Sent to the frontend as a fixed code, never as raw error text."""

    ACCESS_DENIED = "access_denied"       # the user clicked Cancel on Google's screen
    GOOGLE_ERROR = "google_error"         # Google reported some other problem
    INVALID_STATE = "invalid_state"       # unknown/expired/reused sign-in attempt
    EXCHANGE_FAILED = "exchange_failed"   # Google rejected the code we sent back


def redirect_to_frontend(**query: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/?{urlencode(query)}")


@router.get("/login")
def google_login():
    url, state, code_verifier = google_calendar.get_authorization_url()
    pending_logins[state] = code_verifier
    return RedirectResponse(url)


@router.get("/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if error:
        reason = SignInFailure.ACCESS_DENIED if error == "access_denied" else SignInFailure.GOOGLE_ERROR
        return redirect_to_frontend(google="error", reason=reason)

    code_verifier = pending_logins.pop(state, None)
    if code is None or code_verifier is None:
        return redirect_to_frontend(google="error", reason=SignInFailure.INVALID_STATE)

    try:
        credentials = google_calendar.exchange_code_for_credentials(code, code_verifier)
    except google_calendar.GoogleCalendarError:
        # The one place a router catches an AppError itself: a page navigation should end on
        # a page, not on a JSON error from the central handler.
        return redirect_to_frontend(google="error", reason=SignInFailure.EXCHANGE_FAILED)

    user.google_credentials_json = credentials.to_json()
    db.commit()
    return redirect_to_frontend(google="connected")


@router.get("/status")
def google_status(user: User = Depends(get_current_user)):
    return {"connected": user.google_credentials_json is not None}
