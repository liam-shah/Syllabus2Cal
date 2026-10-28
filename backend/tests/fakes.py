"""Hand-written fakes for outside services, shared by several test files."""

from app.domain import EventDraft
from app.integrations.google_calendar import GoogleCalendarError


class FakeCalendar:
    """Stands in for GoogleCalendarClient. Remembers every insert it's asked to do."""

    def __init__(self, fail: dict[str, Exception] | None = None):
        # event title -> what Google says for it. A GoogleCalendarError is that event's outcome;
        # anything else makes the whole call raise (a crash).
        self.fail = fail or {}
        self.inserted: list[tuple[str, str]] = []  # (title, event_id)
        self.time_zones: list[str] = []  # the time zone each insert was given
        self.batch_sizes: list[int] = []  # how many events each call sent
        self.credentials_json = '{"token": "refreshed"}'

    def insert_events(self, events: list[tuple[EventDraft, str]], time_zone: str) -> list[str | GoogleCalendarError]:
        self.batch_sizes.append(len(events))
        outcomes: list[str | GoogleCalendarError] = []
        for event, event_id in events:
            error = self.fail.get(event.title)
            if error is None:
                self.inserted.append((event.title, event_id))
                self.time_zones.append(time_zone)
                outcomes.append(event_id)
            elif isinstance(error, GoogleCalendarError):
                outcomes.append(error)
            else:
                raise error
        return outcomes
