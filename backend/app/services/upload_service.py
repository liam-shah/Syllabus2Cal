"""The upload workflow: read a PDF, extract its events with Claude, and store them.

It happens in two steps, because Claude takes about a minute and a request shouldn't wait
that long (Firebase Hosting gives up on a request after 60 seconds):

1. start_upload, during the request: check the limits, save the upload as 'processing'.
2. extract_events, after the response has been sent: call Claude, save the events, and
   mark the upload 'extracted' (or 'failed'). The frontend polls the upload until then.
"""

import math
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.domain import UploadStatus
from app.errors import InvalidInputError, LimitReachedError, NotFoundError
from app.integrations import llm_extraction, pdf_extraction
from app.models import ExtractedEvent, Upload, User, utc_now

LIMIT_WINDOW = timedelta(days=1)
# Longer than Claude ever takes. An upload still 'processing' after this was lost: the
# server restarted (or was shut down) partway through, and nothing is coming to finish it.
EXTRACTION_TIMEOUT = timedelta(minutes=15)
ABANDONED_MESSAGE = "Extraction was interrupted. Please upload the PDF again."


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

    def start_upload(self, filename: str, pdf_bytes: bytes) -> Upload:
        """Check the upload and save it as 'processing'. Quick: Claude isn't called here."""
        # Raises PDFExtractionError (-> 400) before anything is saved. Unreadable files are
        # never saved, so they don't use up the daily allowance.
        raw_text = pdf_extraction.extract_text(pdf_bytes)
        self._check_text_size(raw_text)
        self._check_daily_limit()

        upload = Upload(user=self._user, filename=filename, raw_text=raw_text, status=UploadStatus.PROCESSING)
        self._db.add(upload)
        # Committed straight after the limit check, before Claude runs, so the very next request
        # already counts this upload. (Saving it only after Claude answered let a script send
        # 30 uploads at once, and all 30 passed the check during that minute.)
        self._db.commit()
        return upload

    def extract_events(self, upload: Upload, pdf_bytes: bytes) -> None:
        """Run Claude on a 'processing' upload and save the result. Runs in the background."""
        try:
            tables = pdf_extraction.extract_tables(pdf_bytes)
            drafts = llm_extraction.extract_events(upload.raw_text, tables)
        except llm_extraction.LLMExtractionError as e:
            # Keep the failed attempt (with its raw_text) so it can be inspected later.
            self._mark_failed(upload, str(e))
            return
        except Exception:
            # Anything unexpected still has to end the 'processing' state, or the page would
            # wait forever. Re-raised so it's logged with its traceback.
            self._mark_failed(upload, "Something went wrong while extracting events. Please try again.")
            raise

        # The events and the new status are saved in one transaction: all or nothing.
        upload.events = [ExtractedEvent.from_draft(draft) for draft in drafts]
        upload.status = UploadStatus.EXTRACTED
        self._db.commit()

    def _mark_failed(self, upload: Upload, reason: str) -> None:
        upload.status = UploadStatus.FAILED
        upload.error_message = reason
        self._db.commit()

    def _check_daily_limit(self) -> None:
        # Every saved upload counts, including failed and still-processing ones: each one is a
        # Claude call that was (or is being) paid for. The uploads table already records this, so no separate counter is needed.
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
        if not raw_text.strip():
            # Claude only gets the text, so it would find nothing - don't pay for that call.
            raise InvalidInputError(
                "This PDF has no text in it, which usually means it's a scan or a photo of a page. "
                "Try a PDF that was exported from a document, where you can select the text."
            )
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
        if upload.status is UploadStatus.PROCESSING and utc_now() - upload.created_at > EXTRACTION_TIMEOUT:
            self._give_up_on(upload)
        return upload

    def _give_up_on(self, upload: Upload) -> None:
        # Checked when someone looks at the upload, rather than by a timer, so it works however
        # the job was lost and needs no scheduler. The WHERE makes it safe if the job finishes at
        # this exact moment: the database only changes the row if it's *still* processing.
        self._db.execute(
            update(Upload)
            .where(Upload.id == upload.id, Upload.status == UploadStatus.PROCESSING)
            .values(status=UploadStatus.FAILED, error_message=ABANDONED_MESSAGE)
        )
        self._db.commit()
        self._db.refresh(upload)

    def get_events(self, upload_id: int) -> list[ExtractedEvent]:
        upload = self.get_upload(upload_id)
        return list(self._db.scalars(
            select(ExtractedEvent)
            .where(ExtractedEvent.upload_id == upload.id)
            .order_by(ExtractedEvent.start_date, ExtractedEvent.id)
        ))


def extract_in_background(session_factory: sessionmaker, upload_id: int, pdf_bytes: bytes) -> None:
    """The background job for step 2: give extract_events a database session of its own.

    It runs after the response has been sent, when the request's session is already closed.
    """
    # shortcut: FastAPI BackgroundTasks run inside the web server's process, so a restart loses
    # jobs that are running (get_upload then gives up on them). Move to a real queue (e.g.
    # Cloud Tasks) before Cloud Run, which also slows the CPU down once a response is sent.
    with session_factory() as db:
        upload = db.get(Upload, upload_id)
        UploadService(db, upload.user).extract_events(upload, pdf_bytes)
