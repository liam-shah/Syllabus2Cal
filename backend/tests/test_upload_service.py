from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.domain import EventDraft, EventStatus, UploadStatus
from app.errors import InvalidInputError, LimitReachedError, NotFoundError
from app.integrations.llm_extraction import LLMExtractionError
from app.integrations.pdf_extraction import PDFExtractionError
from app.models import ExtractedEvent, Upload, User, utc_now
from app.services.upload_service import UploadLimits, UploadService

PDF_BYTES = (Path(__file__).parent / "fixtures" / "cpsc213_schedule_current.pdf").read_bytes()

DRAFTS = [
    EventDraft(title="Lecture 1b: Pointers", start_date=date(2026, 10, 1), date_is_approximate=False),
    EventDraft(title="Lab L1: Numbers & Memory", start_date=date(2026, 9, 21), date_is_approximate=True),
]


def claude_returns(drafts):
    # Replace the Claude call (no API cost, no network) with a fixed answer.
    return patch("app.integrations.llm_extraction.extract_events", return_value=drafts)


def claude_fails(message):
    return patch("app.integrations.llm_extraction.extract_events", side_effect=LLMExtractionError(message))


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_process_pdf_saves_the_upload_and_its_events(db, user):
    with claude_returns(DRAFTS) as mock_extract:
        upload = UploadService(db, user).process_pdf("cpsc213.pdf", PDF_BYTES)

    assert upload.status is UploadStatus.EXTRACTED
    assert [event.title for event in upload.events] == [draft.title for draft in DRAFTS]
    assert all(e.status is EventStatus.PENDING_REVIEW for e in upload.events)
    # Exact dates start ticked, approximate ones unticked (DRAFTS has one of each).
    assert {e.title: e.included for e in upload.events} == {
        "Lecture 1b: Pointers": True,
        "Lab L1: Numbers & Memory": False,
    }

    raw_text, tables = mock_extract.call_args.args  # Claude was given the real PDF's text and tables
    assert "Sep 14-18" in raw_text and len(tables) >= 1


def test_get_events_returns_them_sorted_by_date(db, user):
    service = UploadService(db, user)
    with claude_returns(DRAFTS):
        upload = service.process_pdf("cpsc213.pdf", PDF_BYTES)

    dates = [event.start_date for event in service.get_events(upload.id)]
    assert dates == sorted(dates)


def test_invalid_pdf_raises_and_saves_nothing(db, user):
    with claude_returns(DRAFTS) as mock_extract, pytest.raises(PDFExtractionError):
        UploadService(db, user).process_pdf("notes.pdf", b"not a pdf")

    assert count(db, Upload) == 0
    mock_extract.assert_not_called()  # never pay for a Claude call on a broken file


def test_failed_extraction_is_saved_as_failed_with_no_events(db, user):
    with claude_fails("reply was cut off"), pytest.raises(LLMExtractionError):
        UploadService(db, user).process_pdf("cpsc213.pdf", PDF_BYTES)

    upload = db.scalars(select(Upload)).one()
    assert upload.status is UploadStatus.FAILED
    assert upload.error_message == "reply was cut off"
    assert "Sep 14-18" in upload.raw_text  # kept for debugging the prompt later
    assert count(db, ExtractedEvent) == 0


def test_missing_upload_raises_not_found(db, user):
    with pytest.raises(NotFoundError):
        UploadService(db, user).get_upload(999)


def test_another_users_upload_looks_like_it_does_not_exist(db, user):
    other_user = User()
    db.add(other_user)
    db.commit()
    with claude_returns(DRAFTS):
        their_upload = UploadService(db, other_user).process_pdf("theirs.pdf", PDF_BYTES)

    with pytest.raises(NotFoundError):
        UploadService(db, user).get_upload(their_upload.id)
    with pytest.raises(NotFoundError):
        UploadService(db, user).get_events(their_upload.id)


# --- Limits ------------------------------------------------------------------------------

def add_past_upload(db, user, hours_ago: float, status=UploadStatus.EXTRACTED) -> Upload:
    upload = Upload(user=user, filename="old.pdf", raw_text="...", status=status,
                    created_at=utc_now() - timedelta(hours=hours_ago))
    db.add(upload)
    db.commit()
    return upload


def test_uploads_are_allowed_up_to_the_daily_limit(db, user):
    add_past_upload(db, user, hours_ago=1)
    with claude_returns(DRAFTS):
        UploadService(db, user, UploadLimits(per_day=2)).process_pdf("cpsc213.pdf", PDF_BYTES)  # the 2nd: fine
    assert count(db, Upload) == 2


def test_one_more_is_refused_without_calling_claude_or_saving(db, user):
    add_past_upload(db, user, hours_ago=1)
    add_past_upload(db, user, hours_ago=2)

    with claude_returns(DRAFTS) as mock_extract, pytest.raises(LimitReachedError, match="limit of 2 uploads per day"):
        UploadService(db, user, UploadLimits(per_day=2)).process_pdf("cpsc213.pdf", PDF_BYTES)

    mock_extract.assert_not_called()
    assert count(db, Upload) == 2


def test_the_refusal_says_when_a_slot_frees_up(db, user):
    # The older of the two (20 hours ago) stops counting 4 hours from now.
    add_past_upload(db, user, hours_ago=20)
    add_past_upload(db, user, hours_ago=1)

    with pytest.raises(LimitReachedError, match="in about 4 hours") as refused:
        UploadService(db, user, UploadLimits(per_day=2)).process_pdf("cpsc213.pdf", PDF_BYTES)
    assert timedelta(hours=3, minutes=59) < refused.value.retry_after <= timedelta(hours=4)


def test_uploads_older_than_a_day_stop_counting(db, user):
    add_past_upload(db, user, hours_ago=25)
    with claude_returns(DRAFTS):
        UploadService(db, user, UploadLimits(per_day=1)).process_pdf("cpsc213.pdf", PDF_BYTES)


def test_failed_extractions_still_count(db, user):
    # The Claude call was made (and paid for) even though it failed.
    add_past_upload(db, user, hours_ago=1, status=UploadStatus.FAILED)
    with pytest.raises(LimitReachedError):
        UploadService(db, user, UploadLimits(per_day=1)).process_pdf("cpsc213.pdf", PDF_BYTES)


def test_unreadable_files_do_not_use_up_the_allowance(db, user):
    service = UploadService(db, user, UploadLimits(per_day=1))
    with pytest.raises(PDFExtractionError):
        service.process_pdf("notes.pdf", b"not a pdf")
    with claude_returns(DRAFTS):
        service.process_pdf("cpsc213.pdf", PDF_BYTES)  # still allowed


def test_each_user_has_their_own_allowance(db, user):
    someone_else = User(google_subject="google-someone-else")
    db.add(someone_else)
    db.commit()
    add_past_upload(db, someone_else, hours_ago=1)

    with claude_returns(DRAFTS):
        UploadService(db, user, UploadLimits(per_day=1)).process_pdf("cpsc213.pdf", PDF_BYTES)


def test_a_pdf_with_too_much_text_is_refused_before_claude(db, user):
    with claude_returns(DRAFTS) as mock_extract, pytest.raises(InvalidInputError, match="too much text"):
        UploadService(db, user, UploadLimits(max_text_chars=100)).process_pdf("cpsc213.pdf", PDF_BYTES)

    mock_extract.assert_not_called()
    assert count(db, Upload) == 0


def test_the_real_schedule_fits_comfortably_under_the_default_text_limit():
    # Guards the default: if this fails, the limit would refuse real syllabi.
    from app.integrations import pdf_extraction
    assert len(pdf_extraction.extract_text(PDF_BYTES)) * 10 < UploadLimits().max_text_chars
