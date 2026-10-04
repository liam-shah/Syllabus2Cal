"""Pydantic models describing what the API sends and accepts.

These are separate from the SQLAlchemy models on purpose: they list exactly
which fields leave the server (e.g. never raw_text or Google credentials).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.domain import EventStatus, UploadStatus


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: UploadStatus
    error_message: str | None
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    upload_id: int
    title: str
    start_date: date
    date_is_approximate: bool
    start_time: str | None
    end_time: str | None
    location: str | None
    description: str | None
    source_snippet: str | None
    included: bool
    status: EventStatus
    google_event_id: str | None
    sync_error: str | None
