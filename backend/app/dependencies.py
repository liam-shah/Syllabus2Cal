"""FastAPI dependencies: how routes get a user and a service for each request.

FastAPI caches dependencies within a request, so every Depends(get_db) below
receives the same session.
"""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import session_cookie
from app.db import get_db
from app.errors import NotSignedInError
from app.integrations.google_calendar import GoogleCalendarClient
from app.models import User
from app.services.auth_service import AuthService
from app.services.event_service import EventService
from app.services.sync_service import CalendarFactory, SyncService
from app.services.upload_service import UploadService


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_optional_user(request: Request, auth: AuthService = Depends(get_auth_service)) -> User | None:
    """The signed-in user, or None. For the few routes that also work signed out."""
    token = session_cookie.read_token(request)
    return auth.user_for_token(token) if token is not None else None


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    """The signed-in user. Every route that touches someone's data depends on this, so a
    request without a valid session is turned away (401) before any of that code runs."""
    if user is None:
        raise NotSignedInError("You're not signed in. Sign in with Google to continue.")
    return user


def get_upload_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadService:
    return UploadService(db, user)


def get_event_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventService:
    return EventService(db, user)


def get_calendar_factory() -> CalendarFactory:
    # Its own dependency so HTTP tests can swap in a fake calendar with dependency_overrides.
    return GoogleCalendarClient.from_credentials_json


def get_sync_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    uploads: UploadService = Depends(get_upload_service),
    open_calendar: CalendarFactory = Depends(get_calendar_factory),
) -> SyncService:
    return SyncService(db, user, uploads, open_calendar)
