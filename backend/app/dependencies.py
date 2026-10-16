"""FastAPI dependencies: how routes get a user and a service for each request.

FastAPI caches dependencies within a request, so every Depends(get_db) below
receives the same session.
"""

from collections.abc import Callable
from functools import partial

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from app import session_cookie
from app.config import settings
from app.db import SessionLocal, get_db
from app.errors import NotFoundError, NotSignedInError
from app.integrations import cloud_tasks
from app.integrations.google_calendar import GoogleCalendarClient
from app.models import User
from app.services.auth_service import AuthService
from app.services.event_service import EventService
from app.services.sync_service import CalendarFactory, SyncService
from app.services.upload_service import UploadLimits, UploadService


def get_session_factory() -> sessionmaker:
    # Background jobs outlive the request, so they open sessions of their own instead of
    # using get_db's. A dependency, so tests can point jobs at the test database.
    return SessionLocal


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
    return UploadService(db, user, UploadLimits(per_day=settings.uploads_per_day))


def get_event_service(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventService:
    return EventService(db, user)


TaskTokenVerifier = Callable[[str], None]  # raises TaskTokenError for a token not from our queue


def get_task_token_verifier() -> TaskTokenVerifier | None:
    """How to check a Cloud Tasks token, or None when the queue isn't configured (locally).
    Its own dependency so HTTP tests can swap in a fake check."""
    if not (settings.service_url and settings.tasks_service_account):
        return None
    return partial(cloud_tasks.verify_task_token, audience=settings.service_url,
                   service_account=settings.tasks_service_account)


def require_cloud_tasks(
    authorization: str | None = Header(default=None),
    verify: TaskTokenVerifier | None = Depends(get_task_token_verifier),
) -> None:
    """Turn away anything but our Cloud Tasks queue, before any route code runs."""
    if verify is None:
        raise NotFoundError("Not found")  # no queue configured, so the worker route doesn't exist
    scheme, _, token = (authorization or "").partition(" ")
    if scheme != "Bearer" or not token:
        raise cloud_tasks.TaskTokenError("This request isn't from the extraction queue.")
    verify(token)


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
