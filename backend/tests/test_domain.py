from datetime import date

import pytest
from pydantic import ValidationError

from app.domain import EventDraft, EventUpdate


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


@pytest.mark.parametrize("times", [{"start_time": "14:00", "end_time": "13:00"}, {"end_time": "15:00"},
                                   {"start_time": "2pm", "end_time": "15:00"}])
def test_an_end_time_the_edit_rules_would_reject_moves_to_description(times):
    # Otherwise every later edit (even unticking) would fail the end-after-start check.
    draft = make_draft(**times)
    assert draft.end_time is None
    assert draft.description.endswith(f"End time from PDF: {times['end_time']}")


def test_start_date_is_parsed_from_iso_text():
    # Claude's JSON has dates as text; EventDraft turns them into real date objects.
    draft = EventDraft.model_validate({"title": "Lab", "start_date": "2026-09-21", "date_is_approximate": True})
    assert draft.start_date == date(2026, 9, 21)


# --- EventUpdate: a person's edit is validated strictly ------------------------------------

def test_update_only_reports_the_fields_that_were_sent():
    assert EventUpdate.model_validate({"included": False}).changes() == {"included": False}
    assert EventUpdate.model_validate({"location": None}).changes() == {"location": None}


def test_unreadable_time_from_a_person_is_rejected_not_moved():
    # Unlike EventDraft (Claude's output), a person gets told so they can fix it.
    with pytest.raises(ValidationError):
        EventUpdate(start_time="2pm")


@pytest.mark.parametrize("payload", [{"title": None}, {"title": "   "}, {"start_date": None}, {"included": None}])
def test_required_fields_cannot_be_cleared(payload):
    with pytest.raises(ValidationError):
        EventUpdate.model_validate(payload)


def test_fields_the_app_controls_cannot_be_sent():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EventUpdate.model_validate({"status": "synced"})


def test_text_is_trimmed_and_blank_optional_text_becomes_empty():
    update = EventUpdate(title="  Lab L1  ", location="   ", description="")
    assert update.changes() == {"title": "Lab L1", "location": None, "description": None}
