"""Reviewing events: looking them up for the current user and saving their edits."""

from sqlalchemy.orm import Session

from app.domain import EventUpdate
from app.errors import NotFoundError
from app.models import ExtractedEvent, User


class EventService:
    """Event operations for one user.

    The editing rules themselves live on ExtractedEvent.apply_changes; this class finds the
    event, checks it belongs to the user, and commits.
    """

    def __init__(self, db: Session, user: User):
        self._db = db
        self._user = user

    def get_event(self, event_id: int) -> ExtractedEvent:
        event = self._db.get(ExtractedEvent, event_id)
        # Someone else's event looks exactly like a missing one (prevents IDOR).
        if event is None or event.upload.user_id != self._user.id:
            raise NotFoundError("Event not found")
        return event

    def update_event(self, event_id: int, update: EventUpdate) -> ExtractedEvent:
        event = self.get_event(event_id)
        event.apply_changes(update)  # raises before changing anything if the edit isn't allowed
        self._db.commit()
        return event
