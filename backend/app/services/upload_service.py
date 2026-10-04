"""The upload workflow: read a PDF, extract its events with Claude, and store them."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import UploadStatus
from app.errors import NotFoundError
from app.integrations import llm_extraction, pdf_extraction
from app.models import ExtractedEvent, Upload, User


class UploadService:
    """Everything the app does with uploads, for one user.

    Routers call these methods; they never touch the database or the integrations
    directly. Errors are raised as AppError subclasses and turned into HTTP
    responses in one place (main.py).
    """

    def __init__(self, db: Session, user: User):
        self._db = db
        self._user = user

    def process_pdf(self, filename: str, pdf_bytes: bytes) -> Upload:
        # Raises PDFExtractionError (-> 400) before anything is saved.
        raw_text = pdf_extraction.extract_text(pdf_bytes)
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
