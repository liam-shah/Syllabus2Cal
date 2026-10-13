import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response

from app.domain import EventDraft
from app.integrations.google_calendar import (
    GoogleAuthError,
    GoogleCalendarClient,
    GoogleCalendarError,
    build_event_body,
)

LAB = EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=False)


def google_error(status: int, message: str, reason: str) -> HttpError:
    """An HttpError shaped like the ones Google's API really returns."""
    body = {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}
    return HttpError(Response({"status": str(status)}), json.dumps(body).encode(), uri="https://www.googleapis.com/calendar/v3")


def client_whose_insert(result=None, raises: Exception | None = None):
    """A GoogleCalendarClient whose (fake) Google API returns `result` or raises `raises`."""
    service = MagicMock()
    execute = service.events.return_value.insert.return_value.execute
    if raises is not None:
        execute.side_effect = raises
    else:
        execute.return_value = result
    with patch("app.integrations.google_calendar.build", return_value=service):
        client = GoogleCalendarClient(credentials=MagicMock())
    return client, service


def test_insert_sends_our_event_id_to_google():
    client, service = client_whose_insert(result={"id": "abc12345"})

    assert client.insert_event(LAB, "abc12345") == "abc12345"
    body = service.events.return_value.insert.call_args.kwargs["body"]
    assert body["id"] == "abc12345"
    assert body["summary"] == "Lab L1"


def test_a_duplicate_id_means_the_event_is_already_there():
    client, _ = client_whose_insert(raises=google_error(409, "The requested identifier already exists.", "duplicate"))
    assert client.insert_event(LAB, "abc12345") == "abc12345"


def test_other_conflicts_are_not_mistaken_for_success():
    client, _ = client_whose_insert(raises=google_error(409, "Something else conflicted.", "conflict"))
    with pytest.raises(GoogleCalendarError):
        client.insert_event(LAB, "abc12345")


def test_a_rejected_sign_in_is_its_own_error():
    client, _ = client_whose_insert(raises=google_error(401, "Invalid Credentials", "authError"))
    with pytest.raises(GoogleAuthError, match="reconnect"):
        client.insert_event(LAB, "abc12345")


def test_other_rejections_give_a_short_readable_reason():
    client, _ = client_whose_insert(raises=google_error(400, "Bad Request", "invalid"))
    with pytest.raises(GoogleCalendarError) as caught:
        client.insert_event(LAB, "abc12345")
    assert not isinstance(caught.value, GoogleAuthError)
    assert str(caught.value) == "Google Calendar rejected this event (400: Bad Request)"


def test_all_day_event_ends_the_next_day():
    body = build_event_body(EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=False))
    assert body["start"] == {"date": "2026-09-21"}
    assert body["end"] == {"date": "2026-09-22"}


def test_approximate_date_is_noted_in_description():
    body = build_event_body(EventDraft(title="Lab L1", start_date=date(2026, 9, 21),
                                       date_is_approximate=True, description="Lab"))
    assert body["description"].startswith("Date approximate")
    assert body["description"].endswith("Lab")


def test_timed_event_defaults_to_one_hour():
    body = build_event_body(EventDraft(title="Lecture", start_date=date(2026, 9, 22),
                                       start_time="14:00", date_is_approximate=False))
    assert body["start"] == {"dateTime": "2026-09-22T14:00:00", "timeZone": "America/Vancouver"}
    assert body["end"] == {"dateTime": "2026-09-22T15:00:00", "timeZone": "America/Vancouver"}


def test_location_is_sent_when_present():
    with_location = build_event_body(EventDraft(title="Lab", start_date=date(2026, 9, 21),
                                                date_is_approximate=False, location="ICCS 005"))
    without_location = build_event_body(EventDraft(title="Lab", start_date=date(2026, 9, 21),
                                                   date_is_approximate=False))
    assert with_location["location"] == "ICCS 005"
    assert "location" not in without_location
