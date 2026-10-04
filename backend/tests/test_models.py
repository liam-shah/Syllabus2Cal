from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain import EventDraft, EventStatus, UploadStatus
from app.models import ExtractedEvent, Upload

DRAFT = EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=True,
                   start_time="10:00", location="ICCS 005", source_snippet="L1: Numbers & Memory")


def save_event(db, user, draft: EventDraft = DRAFT) -> ExtractedEvent:
    upload = Upload(user=user, filename="test.pdf", raw_text="...", status=UploadStatus.EXTRACTED)
    upload.events = [ExtractedEvent.from_draft(draft)]
    db.add(upload)
    db.commit()
    return upload.events[0]


def test_draft_survives_a_round_trip_through_the_database(db, user):
    event = save_event(db, user)
    db.expire_all()  # force a fresh read from the database, not the cached object
    assert event.to_draft() == DRAFT


def test_new_events_default_to_pending_review_and_included(db, user):
    event = save_event(db, user)
    assert event.status is EventStatus.PENDING_REVIEW
    assert event.included is True


def test_status_is_stored_as_its_value_not_its_name(db, user):
    event = save_event(db, user)
    stored = db.execute(text("SELECT status FROM extracted_events WHERE id = :id"), {"id": event.id}).scalar()
    assert stored == "pending_review"


def test_database_rejects_an_unknown_status(db, user):
    # Bypasses Python entirely - proves the CHECK constraint lives in the database itself.
    event = save_event(db, user)
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        db.execute(text("UPDATE extracted_events SET status = 'synched' WHERE id = :id"), {"id": event.id})
