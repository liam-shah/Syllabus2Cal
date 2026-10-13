"""Syncing reviewed events into the user's Google Calendar."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.errors import ConflictError
from app.integrations.google_calendar import GoogleAuthError, GoogleCalendarClient, GoogleCalendarError
from app.models import ExtractedEvent, User
from app.services.upload_service import UploadService

# How to open a calendar connection from saved credentials. A parameter (not hard-coded) so
# tests can pass a fake calendar instead of patching the Google library.
CalendarFactory = Callable[[str], GoogleCalendarClient]


class GoogleNotConnectedError(ConflictError):
    """Syncing needs a Google connection first."""


class SyncService:
    """Sends an upload's ticked events to Google Calendar, one at a time.

    Unlike an upload (one all-or-nothing transaction), every event is committed as soon as
    Google answers. A database rollback can't delete an event that's already in Google
    Calendar, so the database has to record each success immediately - otherwise a retry
    after a crash would send those events again.
    """

    def __init__(
        self,
        db: Session,
        user: User,
        uploads: UploadService,
        open_calendar: CalendarFactory = GoogleCalendarClient.from_credentials_json,
    ):
        self._db = db
        self._user = user
        self._uploads = uploads
        self._open_calendar = open_calendar

    def sync_upload(self, upload_id: int) -> list[ExtractedEvent]:
        """Sync every ticked, not-yet-synced event. Returns the events it attempted."""
        events = [event for event in self._uploads.get_events(upload_id) if event.is_waiting_to_sync]

        if self._user.google_credentials_json is None:
            raise GoogleNotConnectedError("Connect Google Calendar before syncing.")
        if not events:
            return []

        calendar = self._open_calendar(self._user.google_credentials_json)  # may refresh the token
        try:
            for event in events:
                self._sync_one(calendar, event)
        finally:
            # Even if we stopped early, keep the refreshed token so the next sync can use it.
            self._user.google_credentials_json = calendar.credentials_json
            self._db.commit()
        return events

    def _sync_one(self, calendar: GoogleCalendarClient, event: ExtractedEvent) -> None:
        # Save the key *before* contacting Google: if we crash after Google creates the event
        # but before we record it, the retry sends the same key and can't create a duplicate.
        sync_key = event.ensure_sync_key()
        self._db.commit()

        try:
            event.mark_synced(calendar.insert_event(event.to_draft(), sync_key))
        except GoogleAuthError:
            raise  # every remaining event would fail the same way, so stop and say "reconnect"
        except GoogleCalendarError as e:
            event.mark_sync_failed(str(e))  # one bad event shouldn't stop the others
        self._db.commit()
