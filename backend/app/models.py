"""SQLAlchemy models: how users, uploads, and events are stored in the database."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain import EventDraft, EventStatus, UploadStatus


def status_column_type(enum_class: type[StrEnum], name: str) -> Enum:
    """A text column that only accepts the enum's values, enforced by a CHECK constraint."""
    return Enum(
        enum_class,
        name=name,
        native_enum=False,          # plain VARCHAR + CHECK, the same on SQLite and PostgreSQL
        create_constraint=True,     # the database itself rejects unknown values
        length=20,
        values_callable=lambda members: [member.value for member in members],  # store "synced", not "SYNCED"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_credentials_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    uploads: Mapped[list["Upload"]] = relationship(back_populates="user")


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str]
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[UploadStatus] = mapped_column(status_column_type(UploadStatus, "upload_status"))
    error_message: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="uploads")
    events: Mapped[list["ExtractedEvent"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan"
    )


class ExtractedEvent(Base):
    __tablename__ = "extracted_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"))
    title: Mapped[str]
    start_date: Mapped[date]
    date_is_approximate: Mapped[bool]
    start_time: Mapped[str | None]
    end_time: Mapped[str | None]
    location: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)
    source_snippet: Mapped[str | None] = mapped_column(Text)
    included: Mapped[bool] = mapped_column(default=True)
    status: Mapped[EventStatus] = mapped_column(
        status_column_type(EventStatus, "event_status"), default=EventStatus.PENDING_REVIEW
    )
    google_event_id: Mapped[str | None]
    sync_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    upload: Mapped["Upload"] = relationship(back_populates="events")

    @classmethod
    def from_draft(cls, draft: EventDraft) -> "ExtractedEvent":
        # EventDraft's fields match these columns one-to-one; if they ever drift apart,
        # this raises a TypeError immediately instead of silently dropping data.
        return cls(**draft.model_dump())

    def to_draft(self) -> EventDraft:
        return EventDraft.model_validate(self, from_attributes=True)
