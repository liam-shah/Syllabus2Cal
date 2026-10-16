"""SyncService with a fake calendar: no network, no patching - the fake is passed in."""

import re
from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.domain import EventDraft, EventStatus, UploadStatus
from app.errors import ConflictError, NotFoundError
from app.integrations.google_calendar import GoogleAuthError, GoogleCalendarError
from app.models import ExtractedEvent, Upload, User
from app.services.sync_service import GoogleNotConnectedError, SyncService
from app.services.upload_service import UploadService
from tests.fakes import FakeCalendar


def add_upload(db, user, *events: tuple[str, bool, EventStatus]) -> Upload:
    """events: (title, included, status)"""
    upload = Upload(user=user, filename="test.pdf", raw_text="...", status=UploadStatus.EXTRACTED)
    for day, (title, included, status) in enumerate(events, start=1):
        row = ExtractedEvent.from_draft(EventDraft(title=title, start_date=date(2026, 9, day), date_is_approximate=False))
        row.included, row.status = included, status
        upload.events.append(row)
    db.add(upload)
    db.commit()
    return upload


@pytest.fixture
def connected_user(db, user):
    user.google_credentials_json = '{"token": "saved"}'
    db.commit()
    return user


def make_service(db, user, calendar: FakeCalendar) -> SyncService:
    return SyncService(db, user, UploadService(db, user), open_calendar=lambda credentials_json: calendar)


def statuses(db, upload) -> dict[str, EventStatus]:
    db.expire_all()  # read what's really in the database
    return {event.title: event.status for event in db.get(Upload, upload.id).events}


PENDING = EventStatus.PENDING_REVIEW
TORONTO = "America/Toronto"


def test_syncs_only_ticked_events_that_are_not_in_the_calendar_yet(db, connected_user):
    upload = add_upload(
        db, connected_user,
        ("Lecture", True, PENDING),
        ("Unticked lab", False, PENDING),
        ("Already synced", True, EventStatus.SYNCED),
        ("Failed last time", True, EventStatus.SYNC_FAILED),
    )
    calendar = FakeCalendar()

    attempted = make_service(db, connected_user, calendar).sync_upload(upload.id, TORONTO)

    assert [title for title, _ in calendar.inserted] == ["Lecture", "Failed last time"]
    assert [event.title for event in attempted] == ["Lecture", "Failed last time"]
    assert statuses(db, upload) == {
        "Lecture": EventStatus.SYNCED,
        "Unticked lab": PENDING,
        "Already synced": EventStatus.SYNCED,
        "Failed last time": EventStatus.SYNCED,
    }


def test_each_event_is_sent_with_its_own_valid_google_event_id(db, connected_user):
    upload = add_upload(db, connected_user, ("A", True, PENDING), ("B", True, PENDING))
    calendar = FakeCalendar()

    make_service(db, connected_user, calendar).sync_upload(upload.id, TORONTO)

    ids = [event_id for _, event_id in calendar.inserted]
    assert len(set(ids)) == 2
    # Google's rule for custom IDs: 5-1024 characters from base32hex (0-9, a-v).
    assert all(re.fullmatch(r"[0-9a-v]{5,1024}", event_id) for event_id in ids)
    db.expire_all()
    assert sorted(e.google_event_id for e in db.get(Upload, upload.id).events) == sorted(ids)


def test_one_failed_event_does_not_stop_the_others(db, connected_user):
    upload = add_upload(db, connected_user, ("Good", True, PENDING), ("Bad", True, PENDING), ("Also good", True, PENDING))
    calendar = FakeCalendar(fail={"Bad": GoogleCalendarError("Google Calendar rejected this event (400: Bad Request)")})

    make_service(db, connected_user, calendar).sync_upload(upload.id, TORONTO)

    assert statuses(db, upload) == {"Good": EventStatus.SYNCED, "Bad": EventStatus.SYNC_FAILED, "Also good": EventStatus.SYNCED}
    bad = next(e for e in db.get(Upload, upload.id).events if e.title == "Bad")
    assert "400: Bad Request" in bad.sync_error


def test_a_rejected_sign_in_stops_the_sync_but_keeps_what_already_worked(db, connected_user):
    upload = add_upload(db, connected_user, ("First", True, PENDING), ("Second", True, PENDING), ("Third", True, PENDING))
    calendar = FakeCalendar(fail={"Second": GoogleAuthError("reconnect Google Calendar")})

    with pytest.raises(GoogleAuthError):
        make_service(db, connected_user, calendar).sync_upload(upload.id, TORONTO)

    # "First" is recorded as synced (committed straight away); nothing after the failure was tried.
    assert statuses(db, upload) == {"First": EventStatus.SYNCED, "Second": PENDING, "Third": PENDING}


def test_a_retry_after_a_crash_reuses_the_same_event_id(db, connected_user):
    # The crash gap: the key is saved before contacting Google, so the retry sends the *same*
    # ID - and Google refuses a duplicate instead of creating a second copy of the event.
    upload = add_upload(db, connected_user, ("Lecture", True, PENDING))
    with pytest.raises(RuntimeError):
        make_service(db, connected_user, FakeCalendar(fail={"Lecture": RuntimeError("server crashed")})).sync_upload(upload.id, TORONTO)
    db.expire_all()
    key_saved_before_the_crash = db.get(Upload, upload.id).events[0].sync_key
    assert key_saved_before_the_crash is not None

    retry = FakeCalendar()
    make_service(db, connected_user, retry).sync_upload(upload.id, TORONTO)

    assert retry.inserted == [("Lecture", key_saved_before_the_crash)]


def test_two_syncs_at_once_send_an_event_with_the_same_id(db, connected_user):
    # Two tabs (or a double click) sync one upload: both read the event before either saves a
    # key. If each then chose its own key, Google would create the event twice.
    upload = add_upload(db, connected_user, ("Lecture", True, PENDING))
    event_id = upload.events[0].id
    calendar = FakeCalendar()
    other_tab = sessionmaker(bind=db.get_bind())()

    def open_calendar_while_the_other_tab_claims_the_key(_credentials_json):
        # Runs after this sync has read its events, before it saves any key.
        other_tab.get(ExtractedEvent, event_id).sync_key = "keyfromtheothertab"
        other_tab.commit()
        return calendar

    service = SyncService(db, connected_user, UploadService(db, connected_user),
                          open_calendar=open_calendar_while_the_other_tab_claims_the_key)
    service.sync_upload(upload.id, TORONTO)
    other_tab.close()

    # The same ID both tabs use, so Google refuses the second insert as a duplicate.
    assert calendar.inserted == [("Lecture", "keyfromtheothertab")]


def test_every_event_is_sent_in_the_time_zone_given(db, connected_user):
    upload = add_upload(db, connected_user, ("A", True, PENDING), ("B", True, PENDING))
    calendar = FakeCalendar()
    make_service(db, connected_user, calendar).sync_upload(upload.id, "Europe/London")
    assert calendar.time_zones == ["Europe/London", "Europe/London"]


def test_refreshed_credentials_are_saved(db, connected_user):
    upload = add_upload(db, connected_user, ("Lecture", True, PENDING))
    make_service(db, connected_user, FakeCalendar()).sync_upload(upload.id, TORONTO)
    db.expire_all()
    assert db.get(User, connected_user.id).google_credentials_json == '{"token": "refreshed"}'


def test_syncing_needs_a_google_connection(db, user):
    upload = add_upload(db, user, ("Lecture", True, PENDING))
    with pytest.raises(GoogleNotConnectedError):
        make_service(db, user, FakeCalendar()).sync_upload(upload.id, TORONTO)
    assert issubclass(GoogleNotConnectedError, ConflictError)  # -> 409


def test_nothing_to_sync_does_not_contact_google(db, connected_user):
    upload = add_upload(db, connected_user, ("Unticked", False, PENDING))

    def must_not_be_called(_credentials_json):
        raise AssertionError("opened a calendar connection with nothing to sync")

    service = SyncService(db, connected_user, UploadService(db, connected_user), open_calendar=must_not_be_called)
    assert service.sync_upload(upload.id, TORONTO) == []


def test_cannot_sync_another_users_upload(db, connected_user):
    other_user = User(google_credentials_json='{"token": "theirs"}')
    db.add(other_user)
    db.commit()
    their_upload = add_upload(db, other_user, ("Theirs", True, PENDING))

    with pytest.raises(NotFoundError):
        make_service(db, connected_user, FakeCalendar()).sync_upload(their_upload.id, TORONTO)
