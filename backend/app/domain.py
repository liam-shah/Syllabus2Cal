"""Core types shared by every layer of the app."""

import re
from datetime import date
from enum import StrEnum
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

TIME_OF_DAY = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")  # 24-hour "HH:MM"


def check_time_of_day(value: str) -> str:
    # A custom check (instead of a regex `pattern`) so the error a person sees is readable.
    if not TIME_OF_DAY.match(value):
        raise ValueError("use 24-hour time like 14:00")
    return value


TimeOfDay = Annotated[str, AfterValidator(check_time_of_day)]


def check_time_zone(value: str) -> str:
    # Checked here, so a bad value is one clear error instead of Google rejecting every event.
    # ValueError covers "" and path tricks like "../etc/passwd"; NotFound covers unknown names.
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("use an IANA time zone like America/Vancouver") from None
    return value


TimeZone = Annotated[str, AfterValidator(check_time_zone)]  # e.g. "America/Toronto"


class UploadStatus(StrEnum):
    PROCESSING = "processing"  # saved, and Claude is still extracting its events
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


class EventUpdate(BaseModel):
    """A change a person asks for while reviewing an event. Only the fields sent are changed.

    Stricter than EventDraft on purpose: Claude's odd values are fixed up quietly so one bad
    field can't fail a whole upload, but a person's input is rejected with a message they can
    act on. Same data, different source, different policy.
    """

    # Unknown fields (e.g. "status" or "google_event_id") are an error, not silently ignored -
    # those are the app's to set, never the client's.
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    start_date: date | None = None
    date_is_approximate: bool | None = None
    start_time: TimeOfDay | None = None
    end_time: TimeOfDay | None = None
    location: str | None = None
    description: str | None = None
    included: bool | None = None

    @field_validator("title")
    @classmethod
    def title_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None  # an explicit null is caught by required_fields_cannot_be_cleared
        if not value.strip():
            raise ValueError("can't be empty")
        return value.strip()

    @field_validator("location", "description")
    @classmethod
    def blank_text_means_empty(cls, value: str | None) -> str | None:
        # A cleared form field arrives as "" - store that as "no value", not an empty string.
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def required_fields_cannot_be_cleared(self) -> "EventUpdate":
        # None means "not sent" for these, so sending an explicit null is a mistake.
        for field_name in ("title", "start_date", "date_is_approximate", "included"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} can't be empty")
        return self

    def changes(self) -> dict:
        """Only the fields that were actually sent."""
        return self.model_dump(exclude_unset=True)
