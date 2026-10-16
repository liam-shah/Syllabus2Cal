from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain import EventDraft, EventStatus, EventUpdate, UploadStatus
from app.errors import ConflictError, InvalidInputError
from app.models import ExtractedEvent, Upload

DRAFT = EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=True,
                   start_time="10:00", location="ICCS 005", source_snippet="L1: Numbers & Memory")


def save_event(db, user, draft: EventDraft = DRAFT) -> ExtractedEvent:
    upload = Upload(user=user, filename="test.pdf", raw_text="...", status=UploadStatus.EXTRACTED)
    upload.events = [ExtractedEvent.from_draft(draft)]
    db.add(upload)
    db.commit()
    return upload.events[0]


def make_event(**overrides) -> ExtractedEvent:
    """An unsaved event - enough for testing the rules, which don't need a database."""
    event = ExtractedEvent.from_draft(DRAFT)
    event.status = EventStatus.PENDING_REVIEW
    for field_name, value in overrides.items():
        setattr(event, field_name, value)
    return event


# --- Storage -------------------------------------------------------------------------------

def test_draft_survives_a_round_trip_through_the_database(db, user):
    event = save_event(db, user)
    db.expire_all()  # force a fresh read from the database, not the cached object
    assert event.to_draft() == DRAFT


def test_new_events_start_pending_review(db, user):
    assert save_event(db, user).status is EventStatus.PENDING_REVIEW


def test_approximate_dates_start_unticked_and_exact_ones_ticked(db, user):
    approximate = save_event(db, user, DRAFT)
    exact = save_event(db, user, DRAFT.model_copy(update={"date_is_approximate": False}))
    assert approximate.included is False
    assert exact.included is True


def test_status_is_stored_as_its_value_not_its_name(db, user):
    event = save_event(db, user)
    stored = db.execute(text("SELECT status FROM extracted_events WHERE id = :id"), {"id": event.id}).scalar()
    assert stored == "pending_review"


def test_database_rejects_an_unknown_status(db, user):
    # Bypasses Python entirely - proves the CHECK constraint lives in the database itself.
    event = save_event(db, user)
    # SQLite says "CHECK constraint failed", Postgres "violates check constraint".
    with pytest.raises(IntegrityError, match="(?i)check constraint"):
        db.execute(text("UPDATE extracted_events SET status = 'synched' WHERE id = :id"), {"id": event.id})


# --- Editing rules (apply_changes) ---------------------------------------------------------

def test_editing_an_event_changes_it_and_marks_it_edited():
    event = make_event()
    event.apply_changes(EventUpdate(title="Lab L1 (moved)", location="ICCS X350"))
    assert (event.title, event.location) == ("Lab L1 (moved)", "ICCS X350")
    assert event.status is EventStatus.EDITED


def test_ticking_an_event_does_not_count_as_editing_it():
    event = make_event()
    event.apply_changes(EventUpdate(included=True))
    assert event.included is True
    assert event.status is EventStatus.PENDING_REVIEW


def test_choosing_a_date_makes_it_exact():
    event = make_event(date_is_approximate=True)
    event.apply_changes(EventUpdate(start_date=date(2026, 9, 23)))
    assert event.start_date == date(2026, 9, 23)
    assert event.date_is_approximate is False


def test_a_date_can_still_be_marked_approximate_explicitly():
    event = make_event(date_is_approximate=True)
    event.apply_changes(EventUpdate(start_date=date(2026, 9, 28), date_is_approximate=True))
    assert event.date_is_approximate is True


def test_editing_a_failed_sync_makes_it_ready_to_retry():
    event = make_event(status=EventStatus.SYNC_FAILED)
    event.apply_changes(EventUpdate(title="Fixed title"))
    assert event.status is EventStatus.EDITED


@pytest.mark.parametrize("update", [EventUpdate(title="New title"), EventUpdate(included=False)])
def test_synced_events_are_locked(update):
    event = make_event(status=EventStatus.SYNCED)
    with pytest.raises(ConflictError):
        event.apply_changes(update)
    assert (event.title, event.included) == ("Lab L1", False)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (EventUpdate(end_time="09:00"), "before the start time"),          # start is 10:00
        (EventUpdate(start_time="12:00", end_time="11:00"), "before the start time"),
        (EventUpdate(start_time=None, end_time="11:00"), "needs a start time"),
    ],
)
def test_bad_time_ranges_are_rejected_without_changing_anything(update, message):
    event = make_event()
    with pytest.raises(InvalidInputError, match=message):
        event.apply_changes(update)
    assert (event.start_time, event.end_time, event.status) == ("10:00", None, EventStatus.PENDING_REVIEW)


def test_clearing_the_start_time_also_needs_the_end_time_cleared():
    event = make_event(end_time="11:00")
    with pytest.raises(InvalidInputError):
        event.apply_changes(EventUpdate(start_time=None))
    event.apply_changes(EventUpdate(start_time=None, end_time=None))  # becomes an all-day event
    assert (event.start_time, event.end_time) == (None, None)
