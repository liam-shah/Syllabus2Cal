"""Hand-written fakes for outside services, shared by several test files."""

from app.domain import EventDraft


class FakeCalendar:
    """Stands in for GoogleCalendarClient. Remembers every insert it's asked to do."""

    def __init__(self, fail: dict[str, Exception] | None = None):
        self.fail = fail or {}  # event title -> exception to raise for it
        self.inserted: list[tuple[str, str]] = []  # (title, event_id)
        self.time_zones: list[str] = []  # the time zone each insert was given
        self.credentials_json = '{"token": "refreshed"}'

    def insert_event(self, event: EventDraft, event_id: str, time_zone: str) -> str:
        if event.title in self.fail:
            raise self.fail[event.title]
        self.inserted.append((event.title, event_id))
        self.time_zones.append(time_zone)
        return event_id
