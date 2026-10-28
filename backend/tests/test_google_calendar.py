import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError
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
TORONTO = "America/Toronto"  # any IANA name the browser could send


def google_error(status: int, message: str, reason: str) -> HttpError:
    """An HttpError shaped like the ones Google's API really returns."""
    body = {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}
    return HttpError(Response({"status": str(status)}), json.dumps(body).encode(), uri="https://www.googleapis.com/calendar/v3")


class FakeBatch:
    """Stands in for googleapiclient's BatchHttpRequest: answers each added request with
    `result`, or with the error `raises`."""

    def __init__(self, callback, result, raises):
        self.callback, self.result, self.raises = callback, result, raises
        self.request_ids: list[str] = []

    def add(self, request, request_id):
        self.request_ids.append(request_id)

    def execute(self):
        for request_id in self.request_ids:
            self.callback(request_id, None if self.raises else self.result, self.raises)


def client_whose_insert(result=None, raises: Exception | None = None):
    """A GoogleCalendarClient whose (fake) Google API returns `result` or `raises` for each insert."""
    service = MagicMock()
    service.new_batch_http_request.side_effect = lambda callback: FakeBatch(callback, result, raises)
    with patch("app.integrations.google_calendar.build", return_value=service):
        client = GoogleCalendarClient(credentials=MagicMock())
    return client, service


def insert_one(client, event=LAB):
    [outcome] = client.insert_events([(event, "abc12345")], TORONTO)
    return outcome


def test_insert_sends_our_event_id_to_google():
    client, service = client_whose_insert(result={"id": "abc12345"})

    assert insert_one(client) == "abc12345"
    body = service.events.return_value.insert.call_args.kwargs["body"]
    assert body["id"] == "abc12345"
    assert body["summary"] == "Lab L1"


def test_events_are_sent_together_and_answered_in_order():
    client, service = client_whose_insert(result={"id": "fromgoogle"})
    second = EventDraft(title="Lab L2", start_date=date(2026, 9, 28), date_is_approximate=False)

    assert client.insert_events([(LAB, "aaaaa1"), (second, "aaaaa2")], TORONTO) == ["fromgoogle", "fromgoogle"]
    assert service.new_batch_http_request.call_count == 1  # one HTTP request for both


def test_a_duplicate_id_means_the_event_is_already_there():
    client, _ = client_whose_insert(raises=google_error(409, "The requested identifier already exists.", "duplicate"))
    assert insert_one(client) == "abc12345"


def test_other_conflicts_are_not_mistaken_for_success():
    client, _ = client_whose_insert(raises=google_error(409, "Something else conflicted.", "conflict"))
    assert isinstance(insert_one(client), GoogleCalendarError)


def test_a_rejected_sign_in_is_its_own_error():
    client, _ = client_whose_insert(raises=google_error(401, "Invalid Credentials", "authError"))
    outcome = insert_one(client)
    assert isinstance(outcome, GoogleAuthError)
    assert "reconnect" in str(outcome)


def test_a_token_google_will_not_renew_mid_sync_is_a_sign_in_error():
    client, service = client_whose_insert(result={"id": "abc12345"})
    service.new_batch_http_request.side_effect = None
    service.new_batch_http_request.return_value.execute.side_effect = RefreshError("invalid_grant")
    assert isinstance(insert_one(client), GoogleAuthError)


def test_other_rejections_give_a_short_readable_reason():
    client, _ = client_whose_insert(raises=google_error(400, "Bad Request", "invalid"))
    outcome = insert_one(client)
    assert not isinstance(outcome, GoogleAuthError)
    assert str(outcome) == "Google Calendar rejected this event (400: Bad Request)"


def test_all_day_event_ends_the_next_day():
    body = build_event_body(EventDraft(title="Lab L1", start_date=date(2026, 9, 21), date_is_approximate=False), TORONTO)
    assert body["start"] == {"date": "2026-09-21"}
    assert body["end"] == {"date": "2026-09-22"}


def test_approximate_date_is_noted_in_description():
    body = build_event_body(EventDraft(title="Lab L1", start_date=date(2026, 9, 21),
                                       date_is_approximate=True, description="Lab"), TORONTO)
    assert body["description"].startswith("Date approximate")
    assert body["description"].endswith("Lab")


def test_timed_event_defaults_to_one_hour_in_the_given_time_zone():
    # The wall-clock time from the PDF, in the syncing person's own time zone (not Vancouver's).
    body = build_event_body(EventDraft(title="Lecture", start_date=date(2026, 9, 22),
                                       start_time="14:00", date_is_approximate=False), TORONTO)
    assert body["start"] == {"dateTime": "2026-09-22T14:00:00", "timeZone": "America/Toronto"}
    assert body["end"] == {"dateTime": "2026-09-22T15:00:00", "timeZone": "America/Toronto"}


def test_insert_sends_the_time_zone_to_google():
    client, service = client_whose_insert(result={"id": "abc12345"})
    timed = EventDraft(title="Lecture", start_date=date(2026, 9, 22), start_time="14:00", date_is_approximate=False)
    insert_one(client, timed)
    body = service.events.return_value.insert.call_args.kwargs["body"]
    assert body["start"]["timeZone"] == "America/Toronto"


def test_location_is_sent_when_present():
    with_location = build_event_body(EventDraft(title="Lab", start_date=date(2026, 9, 21),
                                                date_is_approximate=False, location="ICCS 005"), TORONTO)
    without_location = build_event_body(EventDraft(title="Lab", start_date=date(2026, 9, 21),
                                                   date_is_approximate=False), TORONTO)
    assert with_location["location"] == "ICCS 005"
    assert "location" not in without_location
