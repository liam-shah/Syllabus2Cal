"""Core types shared by every layer of the app."""

import re
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

TIME_OF_DAY = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # 24-hour "HH:MM"


class UploadStatus(StrEnum):
    EXTRACTED = "extracted"
    FAILED = "failed"


class EventStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    EDITED = "edited"
    SYNCED = "synced"
    SYNC_FAILED = "sync_failed"


class EventDraft(BaseModel):
    """One calendar event, independent of where it's stored.

    Claude produces these, the database stores them, and the calendar
    integration consumes them.
    """

    title: str
    start_date: date
    date_is_approximate: bool
    start_time: str | None = Field(default=None, description="24-hour time as HH:MM, e.g. 14:00")
    end_time: str | None = Field(default=None, description="24-hour time as HH:MM, e.g. 15:30")
    location: str | None = None
    description: str | None = None
    source_snippet: str | None = None

    @model_validator(mode="after")
    def move_unreadable_times_to_description(self) -> "EventDraft":
        # One oddly formatted time (e.g. "2pm") shouldn't fail a whole upload, and the
        # calendar code needs HH:MM - so keep the original text visible and drop the time.
        for field_name, label in (("start_time", "Start"), ("end_time", "End")):
            value = getattr(self, field_name)
            if value is not None and not TIME_OF_DAY.match(value):
                note = f"{label} time from PDF: {value}"
                self.description = f"{self.description}\n{note}" if self.description else note
                setattr(self, field_name, None)
        return self
