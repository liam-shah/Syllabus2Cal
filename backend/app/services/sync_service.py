"""Syncing reviewed events into the user's Google Calendar."""

import uuid
from collections.abc import Callable

from sqlalchemy import update
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

    def sync_upload(self, upload_id: int, time_zone: str) -> list[ExtractedEvent]:
        """Sync every ticked, not-yet-synced event, with timed events placed in time_zone
        (an IANA name, already checked). Returns the events it attempted."""
        events = [event for event in self._uploads.get_events(upload_id) if event.is_waiting_to_sync]

        if self._user.google_credentials_json is None:
            raise GoogleNotConnectedError("Connect Google Calendar before syncing.")
        if not events:
            return []

        calendar = self._open_calendar(self._user.google_credentials_json)  # may refresh the token
        try:
            for event in events:
                self._sync_one(calendar, event, time_zone)
        finally:
            # Even if we stopped early, keep the refreshed token so the next sync can use it.
            self._user.google_credentials_json = calendar.credentials_json
            self._db.commit()
        return events

    def _sync_one(self, calendar: GoogleCalendarClient, event: ExtractedEvent, time_zone: str) -> None:
        # Save the key *before* contacting Google: if we crash after Google creates the event
        # but before we record it, the retry sends the same key and can't create a duplicate.
        sync_key = self._claim_sync_key(event)

        try:
            event.mark_synced(calendar.insert_event(event.to_draft(), sync_key, time_zone))
        except GoogleAuthError:
            raise  # every remaining event would fail the same way, so stop and say "reconnect"
        except GoogleCalendarError as e:
            event.mark_sync_failed(str(e))  # one bad event shouldn't stop the others
        self._db.commit()

    def _claim_sync_key(self, event: ExtractedEvent) -> str:
        """The ID to give this event in Google Calendar - chosen once, then reused on every retry.

        Set in the database only if there's no key yet (compare-and-set): two syncs running at
        once (two tabs, a double click) both read "no key", but only one UPDATE matches, so both
        send the *same* ID and Google refuses the second insert as a duplicate.
        """
        self._db.execute(
            update(ExtractedEvent)
            .where(ExtractedEvent.id == event.id, ExtractedEvent.sync_key.is_(None))
            .values(sync_key=uuid.uuid4().hex),  # 32 chars of 0-9a-f: a valid Google event ID
            execution_options={"synchronize_session": False},
        )
        self._db.commit()
        self._db.refresh(event)  # whichever key the database kept: ours, or the other sync's
        return event.sync_key
