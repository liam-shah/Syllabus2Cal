"""Google sign-in routes: /auth/google/login, /callback, /status, and a temporary /test-event."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.domain import EventDraft
from app.integrations import google_calendar
from app.models import User

router = APIRouter(prefix="/auth/google", tags=["auth"])

# Sign-in attempts only last a few seconds, so keeping them in memory is fine.
pending_logins: dict[str, str] = {}  # state -> code_verifier


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
        raise HTTPException(status_code=400, detail=f"Google sign-in was cancelled or failed: {error}")

    code_verifier = pending_logins.pop(state, None)
    if code is None or code_verifier is None:
        raise HTTPException(
            status_code=400,
            detail="Unknown or expired sign-in attempt - start again at /auth/google/login",
        )

    credentials = google_calendar.exchange_code_for_credentials(code, code_verifier)
    user.google_credentials_json = credentials.to_json()
    db.commit()
    return {"connected": True}


@router.get("/status")
def google_status(user: User = Depends(get_current_user)):
    return {"connected": user.google_credentials_json is not None}


# Temporary: delete once POST /events/sync exists.
@router.post("/test-event")
def create_test_event(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.google_credentials_json is None:
        raise HTTPException(status_code=401, detail="Not connected - visit /auth/google/login first")

    credentials = google_calendar.load_credentials(user.google_credentials_json)
    event_id = google_calendar.insert_event(credentials, EventDraft(
        title="Calendar PDF Sync test event",
        start_date=date.today() + timedelta(days=1),
        date_is_approximate=False,
        description="Created by the calendar-pdf-sync standalone test. Safe to delete.",
    ))

    user.google_credentials_json = credentials.to_json()
    db.commit()
    return {"google_event_id": event_id}
