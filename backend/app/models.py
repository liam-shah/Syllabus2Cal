"""SQLAlchemy models: how users, uploads, and events are stored in the database."""

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain import EventDraft, EventStatus, EventUpdate, UploadStatus
from app.errors import ConflictError, InvalidInputError


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


def utc_now() -> datetime:
    """The current time in UTC, without a timezone attached - how every time is stored here.

    SQLite has no timezone-aware column type, so all times are stored as plain UTC.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Who the user is: Google's permanent ID for their account (the ID token's "sub" claim).
    # Not the email address, which a person can change. Nullable only because the user row
    # from before accounts existed has no Google identity.
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None]  # for display only; never used to look anyone up
    google_credentials_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    uploads: Mapped[list["Upload"]] = relationship(back_populates="user")
    login_sessions: Mapped[list["LoginSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_calendar_connected(self) -> bool:
        return self.google_credentials_json is not None


class LoginSession(Base):
    """One signed-in browser. The browser holds a random token; the database holds its hash.

    Keeping sessions in the database (rather than only in a signed cookie) means signing out
    really ends the session: a copied cookie stops working the moment its row is deleted.
    """

    __tablename__ = "login_sessions"

    LIFETIME = timedelta(days=30)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SHA-256 of the token, as 64 hex characters. If the database ever leaked, these
    # couldn't be turned back into working cookies.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    expires_at: Mapped[datetime]

    user: Mapped["User"] = relationship(back_populates="login_sessions")

    @classmethod
    def start(cls, user: User, token_hash: str) -> "LoginSession":
        now = utc_now()
        return cls(user=user, token_hash=token_hash, created_at=now, expires_at=now + cls.LIFETIME)

    def has_expired(self) -> bool:
        return utc_now() >= self.expires_at


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str]
    raw_text: Mapped[str] = mapped_column(Text)
    # The PDF's tables as JSON, saved at upload time with raw_text: together they're everything
    # Claude needs, so the extraction job doesn't need the PDF (a Cloud Task holds at most ~1 MB).
    tables_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[UploadStatus] = mapped_column(status_column_type(UploadStatus, "upload_status"))
    # When an extraction job claimed this upload. Set only while still unset (compare-and-set),
    # so a retried job can't call Claude - and pay - a second time.
    extraction_claimed_at: Mapped[datetime | None]
    error_message: Mapped[str | None]
    # Set by Python (not the database's clock), because the daily limit compares it with utc_now().
    created_at: Mapped[datetime] = mapped_column(default=utc_now, server_default=func.now())

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
    # Idempotency key: the ID we ask Google to give this event. Chosen (and saved) before the
    # first attempt, so a retry after a crash sends the *same* ID and Google refuses a duplicate.
    # Random rather than the row id, which restarts at 1 if the database is ever recreated.
    # A unique *index* (not a constraint): SQLite can add one to an existing table without rebuilding it.
    sync_key: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    sync_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    upload: Mapped["Upload"] = relationship(back_populates="events")

    @classmethod
    def from_draft(cls, draft: EventDraft) -> "ExtractedEvent":
        # EventDraft's fields match these columns one-to-one; if they ever drift apart,
        # this raises a TypeError immediately instead of silently dropping data.
        # Approximate dates start unticked: nothing lands on a guessed day unless the user
        # fixes the date or ticks it on purpose.
        return cls(**draft.model_dump(), included=not draft.date_is_approximate)

    def to_draft(self) -> EventDraft:
        return EventDraft.model_validate(self, from_attributes=True)

    def apply_changes(self, update: EventUpdate) -> None:
        """Apply a user's edit, enforcing the rules every edit must follow.

        Everything is checked before anything changes, so a rejected edit leaves the
        event exactly as it was.
        """
        if self.status is EventStatus.SYNCED:
            raise ConflictError("This event is already in Google Calendar, so it can't be changed here.")

        changes = update.changes()
        # Choosing a date yourself makes it exact - that's the point of fixing an approximate one.
        if "start_date" in changes and "date_is_approximate" not in changes:
            changes["date_is_approximate"] = False

        self._check_times(
            start_time=changes.get("start_time", self.start_time),
            end_time=changes.get("end_time", self.end_time),
        )

        for field_name, value in changes.items():
            setattr(self, field_name, value)

        # Ticking/unticking is a choice about syncing, not a change to the event itself.
        if changes.keys() - {"included"}:
            self.status = EventStatus.EDITED  # also moves SYNC_FAILED back, ready to retry

    # --- Syncing ---------------------------------------------------------------------------

    @property
    def is_waiting_to_sync(self) -> bool:
        """Ticked for the calendar and not there yet (including earlier failed attempts)."""
        return self.included and self.status is not EventStatus.SYNCED

    def mark_synced(self, google_event_id: str) -> None:
        self.status = EventStatus.SYNCED
        self.google_event_id = google_event_id
        self.sync_error = None

    def mark_sync_failed(self, reason: str) -> None:
        self.status = EventStatus.SYNC_FAILED
        self.sync_error = reason

    @staticmethod
    def _check_times(start_time: str | None, end_time: str | None) -> None:
        if end_time is None:
            return
        if start_time is None:
            raise InvalidInputError("An end time needs a start time.")
        if time.fromisoformat(end_time) < time.fromisoformat(start_time):
            raise InvalidInputError("The end time can't be before the start time.")
