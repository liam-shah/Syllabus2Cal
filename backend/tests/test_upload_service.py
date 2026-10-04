from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.domain import EventDraft, EventStatus, UploadStatus
from app.errors import NotFoundError
from app.integrations.llm_extraction import LLMExtractionError
from app.integrations.pdf_extraction import PDFExtractionError
from app.models import ExtractedEvent, Upload, User
from app.services.upload_service import UploadService

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
    assert all(e.status is EventStatus.PENDING_REVIEW and e.included for e in upload.events)

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
