from datetime import date

import pytest

from app.domain import EventDraft, EventStatus, EventUpdate, UploadStatus
from app.errors import NotFoundError
from app.models import ExtractedEvent, Upload, User
from app.services.event_service import EventService

DRAFT = EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=True)


def save_event(db, owner: User) -> ExtractedEvent:
    upload = Upload(user=owner, filename="test.pdf", raw_text="...", status=UploadStatus.EXTRACTED)
    upload.events = [ExtractedEvent.from_draft(DRAFT)]
    db.add(upload)
    db.commit()
    return upload.events[0]


def test_update_is_saved_to_the_database(db, user):
    event = save_event(db, user)

    EventService(db, user).update_event(event.id, EventUpdate(start_date=date(2026, 9, 23), included=True))

    db.expire_all()  # read back from the database, not the object in memory
    saved = db.get(ExtractedEvent, event.id)
    assert (saved.start_date, saved.date_is_approximate, saved.included) == (date(2026, 9, 23), False, True)
    assert saved.status is EventStatus.EDITED


def test_missing_event_raises_not_found(db, user):
    with pytest.raises(NotFoundError):
        EventService(db, user).update_event(999, EventUpdate(included=True))


def test_another_users_event_looks_like_it_does_not_exist(db, user):
    other_user = User()
    db.add(other_user)
    db.commit()
    their_event = save_event(db, other_user)

    with pytest.raises(NotFoundError):
        EventService(db, user).update_event(their_event.id, EventUpdate(title="Mine now"))

    db.expire_all()
    assert db.get(ExtractedEvent, their_event.id).title == "Lab L1"
