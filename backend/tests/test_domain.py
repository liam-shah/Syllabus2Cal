from datetime import date

from app.domain import EventDraft


def make_draft(**overrides) -> EventDraft:
    fields = {"title": "Lecture", "start_date": date(2026, 9, 22), "date_is_approximate": False}
    return EventDraft(**(fields | overrides))


def test_valid_times_are_kept():
    draft = make_draft(start_time="09:30", end_time="10:50")
    assert (draft.start_time, draft.end_time) == ("09:30", "10:50")


def test_unreadable_time_moves_to_description_instead_of_failing():
    draft = make_draft(start_time="2pm")
    assert draft.start_time is None
    assert draft.description == "Start time from PDF: 2pm"


def test_unreadable_time_is_added_after_existing_description():
    draft = make_draft(description="Thursday lecture", end_time="late")
    assert draft.end_time is None
    assert draft.description == "Thursday lecture\nEnd time from PDF: late"


def test_start_date_is_parsed_from_iso_text():
    # Claude's JSON has dates as text; EventDraft turns them into real date objects.
    draft = EventDraft.model_validate({"title": "Lab", "start_date": "2026-09-21", "date_is_approximate": True})
    assert draft.start_date == date(2026, 9, 21)
