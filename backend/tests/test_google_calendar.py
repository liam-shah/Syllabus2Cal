from datetime import date

from app.domain import EventDraft
from app.integrations.google_calendar import build_event_body


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
