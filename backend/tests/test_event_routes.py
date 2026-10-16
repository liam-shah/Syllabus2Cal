"""The /events routes through the real app (HTTP status codes and response shapes)."""

from datetime import date

import pytest

from app.dependencies import get_calendar_factory
from app.domain import EventDraft, EventStatus, UploadStatus
from app.main import app
from app.models import ExtractedEvent, Upload
from tests.fakes import FakeCalendar

DRAFT = EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=True, start_time="10:00")


@pytest.fixture
def event(db, user) -> ExtractedEvent:
    # Owned by the user the `client` fixture is signed in as.
    upload = Upload(user=user, filename="test.pdf", raw_text="...", status=UploadStatus.EXTRACTED)
    upload.events = [ExtractedEvent.from_draft(DRAFT)]
    db.add(upload)
    db.commit()
    return upload.events[0]


def patch(client, event_id: int, body: dict):
    return client.patch(f"/events/{event_id}", json=body)


def test_patch_returns_the_updated_event(client, event):
    response = patch(client, event.id, {"start_date": "2026-09-23", "included": True})

    assert response.status_code == 200
    body = response.json()
    assert (body["start_date"], body["date_is_approximate"], body["included"]) == ("2026-09-23", False, True)
    assert body["status"] == "edited"


def test_invalid_input_is_a_422_listing_the_problem(client, event):
    response = patch(client, event.id, {"start_time": "2pm"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)  # FastAPI's validation-error shape


def test_a_rule_broken_across_fields_is_a_400(client, event):
    response = patch(client, event.id, {"end_time": "09:00"})  # starts at 10:00
    assert response.status_code == 400
    assert response.json() == {"detail": "The end time can't be before the start time."}


def test_editing_a_synced_event_is_a_409(client, db, event):
    event.status = EventStatus.SYNCED
    db.commit()

    response = patch(client, event.id, {"included": False})
    assert response.status_code == 409
    assert "already in Google Calendar" in response.json()["detail"]


def test_missing_event_is_a_404(client):
    assert patch(client, 999, {"included": True}).status_code == 404


# --- POST /events/sync ---------------------------------------------------------------------

def sync(client, upload_id: int, time_zone: str = "America/Toronto"):
    # The browser sends its own IANA time zone with every sync.
    return client.post("/events/sync", params={"upload_id": upload_id, "time_zone": time_zone})


@pytest.fixture
def fake_calendar(client):
    calendar = FakeCalendar()
    app.dependency_overrides[get_calendar_factory] = lambda: (lambda credentials_json: calendar)
    return calendar  # the `client` fixture clears every override afterwards


def test_sync_returns_the_attempted_events_with_their_new_status(client, db, user, event, fake_calendar):
    event.included = True
    user.google_credentials_json = '{"token": "saved"}'
    db.commit()

    response = sync(client, event.upload_id)

    assert response.status_code == 200
    [synced] = response.json()
    assert (synced["id"], synced["status"]) == (event.id, "synced")
    assert synced["google_event_id"] == fake_calendar.inserted[0][1]
    assert fake_calendar.time_zones == ["America/Toronto"]


def test_sync_without_a_google_connection_is_a_409(client, event, fake_calendar):
    response = sync(client, event.upload_id)
    assert response.status_code == 409
    assert response.json() == {"detail": "Connect Google Calendar before syncing."}
    assert fake_calendar.inserted == []


def test_syncing_a_missing_upload_is_a_404(client, fake_calendar):
    assert sync(client, 999).status_code == 404


@pytest.mark.parametrize("time_zone", ["Mars/Olympus", "", "../etc/passwd"])
def test_an_unknown_time_zone_is_refused_before_google_is_contacted(client, db, user, event, fake_calendar, time_zone):
    event.included = True
    user.google_credentials_json = '{"token": "saved"}'
    db.commit()

    response = sync(client, event.upload_id, time_zone=time_zone)

    assert response.status_code == 422
    assert "IANA time zone" in response.text
    assert fake_calendar.inserted == []


def test_syncing_without_a_time_zone_is_refused(client, event, fake_calendar):
    response = client.post("/events/sync", params={"upload_id": event.upload_id})
    assert response.status_code == 422
