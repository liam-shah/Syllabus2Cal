"""The upload workflow: read a PDF, extract its events with Claude, and store them."""

import math
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import UploadStatus
from app.errors import InvalidInputError, LimitReachedError, NotFoundError
from app.integrations import llm_extraction, pdf_extraction
from app.models import ExtractedEvent, Upload, User, utc_now

LIMIT_WINDOW = timedelta(days=1)


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


@dataclass(frozen=True)
class UploadLimits:
    """How much Claude each user may use. Passed in, so tests (and settings) can choose."""

    per_day: int = 10  # uploads in any rolling 24 hours
    # A course schedule is a few thousand characters; the CPSC 213 one is about 2,400.
    # 50,000 (roughly 12k tokens) leaves plenty of room while capping what one upload costs.
    max_text_chars: int = 50_000


class UploadService:
    """Everything the app does with uploads, for one user.

    Routers call these methods; they never touch the database or the integrations
    directly. Errors are raised as AppError subclasses and turned into HTTP
    responses in one place (main.py).
    """

    def __init__(self, db: Session, user: User, limits: UploadLimits = UploadLimits()):
        self._db = db
        self._user = user
        self._limits = limits

    def process_pdf(self, filename: str, pdf_bytes: bytes) -> Upload:
        # Every check runs before Claude is called, so a refused upload costs nothing.
        self._check_daily_limit()
        # Raises PDFExtractionError (-> 400) before anything is saved. Unreadable files are
        # never saved, so they don't use up the daily allowance.
        raw_text = pdf_extraction.extract_text(pdf_bytes)
        self._check_text_size(raw_text)
        tables = pdf_extraction.extract_tables(pdf_bytes)

        upload = Upload(
            user=self._user,
            filename=filename,
            raw_text=raw_text,
            status=UploadStatus.EXTRACTED,
        )
        self._db.add(upload)

        try:
            drafts = llm_extraction.extract_events(raw_text, tables)
        except llm_extraction.LLMExtractionError as e:
            # Keep the failed attempt (with its raw_text) so it can be inspected later.
            upload.status = UploadStatus.FAILED
            upload.error_message = str(e)
            self._db.commit()
            raise

        # The upload and all of its events are saved in one transaction: all or nothing.
        upload.events = [ExtractedEvent.from_draft(draft) for draft in drafts]
        self._db.commit()
        return upload

    def _check_daily_limit(self) -> None:
        # Every saved upload counts, including failed ones: a failed extraction still paid for
        # a Claude call. The uploads table already records this, so no separate counter is needed.
        window_start = utc_now() - LIMIT_WINDOW
        recent = list(self._db.scalars(
            select(Upload.created_at)
            .where(Upload.user_id == self._user.id, Upload.created_at > window_start)
            .order_by(Upload.created_at)
        ))
        if len(recent) < self._limits.per_day:
            return

        # A slot frees up when enough of the oldest recent uploads are more than a day old.
        frees_up_at = recent[len(recent) - self._limits.per_day] + LIMIT_WINDOW
        retry_after = max(frees_up_at - utc_now(), timedelta(0))
        hours = max(1, math.ceil(retry_after.total_seconds() / 3600))
        raise LimitReachedError(
            f"You've reached the limit of {plural(self._limits.per_day, 'upload')} per day. "
            f"You can upload again in about {plural(hours, 'hour')}.",
            retry_after=retry_after,
        )

    def _check_text_size(self, raw_text: str) -> None:
        if len(raw_text) > self._limits.max_text_chars:
            raise InvalidInputError(
                f"This PDF has too much text to be a course schedule ({len(raw_text):,} characters; "
                f"the limit is {self._limits.max_text_chars:,}). Try a PDF with just the schedule pages."
            )

    def get_upload(self, upload_id: int) -> Upload:
        upload = self._db.get(Upload, upload_id)
        # Someone else's upload looks exactly like a missing one (prevents IDOR).
        if upload is None or upload.user_id != self._user.id:
            raise NotFoundError("Upload not found")
        return upload

    def get_events(self, upload_id: int) -> list[ExtractedEvent]:
        upload = self.get_upload(upload_id)
        return list(self._db.scalars(
            select(ExtractedEvent)
            .where(ExtractedEvent.upload_id == upload.id)
            .order_by(ExtractedEvent.start_date, ExtractedEvent.id)
        ))
