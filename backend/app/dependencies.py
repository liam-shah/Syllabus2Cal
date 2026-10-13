"""FastAPI dependencies: how routes get a user and a service for each request.

FastAPI caches dependencies within a request, so every Depends(get_db) below
receives the same session.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.integrations.google_calendar import GoogleCalendarClient
from app.services.event_service import EventService
from app.services.sync_service import CalendarFactory, SyncService
from app.services.upload_service import UploadService
from app.services.users import get_local_user


def get_current_user(db: Session = Depends(get_db)) -> User:
    # Single-user shortcut: the only place in the app that knows there is one user.
    # A multi-user version would look the user up from their login session here.
    return get_local_user(db)


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
