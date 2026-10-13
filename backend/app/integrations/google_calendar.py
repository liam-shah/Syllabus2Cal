"""Google OAuth flow + Calendar API event insertion."""

import json
from datetime import datetime, time, timedelta

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

from app.config import settings
from app.domain import EventDraft
from app.errors import ExternalServiceError

CLIENT_SECRET_PATH = settings.google_client_secret_path
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
# Must exactly match an "Authorized redirect URI" on the OAuth client in Google Cloud Console.
REDIRECT_URI = f"{settings.backend_url}/auth/google/callback"
TIMEZONE = "America/Vancouver"


class GoogleCalendarError(ExternalServiceError):
    """Raised when signing in to Google or creating a calendar event fails."""


class GoogleAuthError(GoogleCalendarError):
    """Google no longer accepts the saved sign-in. Every further request would fail the same way."""


def build_flow(code_verifier: str | None = None) -> Flow:
    return Flow.from_client_secrets_file(
        CLIENT_SECRET_PATH,
        scopes = SCOPES,
        redirect_uri = REDIRECT_URI,
        code_verifier = code_verifier,
    )

def get_authorization_url() -> tuple[str, str, str]:
    flow = build_flow()
    url, state = flow.authorization_url(prompt = "consent")
    return url, state, flow.code_verifier


def exchange_code_for_credentials(code: str, code_verifier: str) -> Credentials:
    flow = build_flow(code_verifier=code_verifier)
    try:
        flow.fetch_token(code=code)
    except OAuth2Error as e:
        raise GoogleCalendarError(f"Could not finish Google sign-in: {e}") from e
    return flow.credentials


def load_credentials(credentials_json: str) -> Credentials:
    credentials = Credentials.from_authorized_user_info(json.loads(credentials_json), SCOPES)
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError as e:
            raise GoogleAuthError(
                "Google access expired or was revoked - reconnect Google Calendar and sync again"
            ) from e
    return credentials


def build_event_body(event: EventDraft) -> dict:
    description = event.description or ""
    if event.date_is_approximate:
        description = (
            "Date approximate: the PDF only gives the week, not the exact day.\n" + description
        ).strip()

    body = {"summary": event.title, "description": description}
    if event.location:
        body["location"] = event.location

    if event.start_time:
        # EventDraft guarantees times are valid "HH:MM", so fromisoformat can't fail here.
        start = datetime.combine(event.start_date, time.fromisoformat(event.start_time))
        if event.end_time:
            end = datetime.combine(event.start_date, time.fromisoformat(event.end_time))
        else:
            end = start + timedelta(hours=1)
        body["start"] = {"dateTime": start.isoformat(), "timeZone": TIMEZONE}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": TIMEZONE}
    else:
        # All-day events: Google treats the end date as exclusive, so end = the next day.
        body["start"] = {"date": event.start_date.isoformat()}
        body["end"] = {"date": (event.start_date + timedelta(days=1)).isoformat()}

    return body


def is_duplicate_id_error(error: HttpError) -> bool:
    """409 means "conflict" in general; only the "duplicate" reason means the ID is already taken."""
    details = error.error_details if isinstance(error.error_details, list) else []
    return error.status_code == 409 and any(
        isinstance(detail, dict) and detail.get("reason") == "duplicate" for detail in details
    )


class GoogleCalendarClient:
    """A connection to one user's primary Google Calendar.

    Built once per sync (building the API client is relatively slow), then used for every event.
    """

    def __init__(self, credentials: Credentials):
        self._credentials = credentials
        # cache_discovery=False: skip a file cache that only logs warnings with google-auth.
        self._service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    @classmethod
    def from_credentials_json(cls, credentials_json: str) -> "GoogleCalendarClient":
        return cls(load_credentials(credentials_json))  # refreshes the access token if needed

    @property
    def credentials_json(self) -> str:
        """The (possibly refreshed) credentials, to save back onto the user afterwards."""
        return self._credentials.to_json()

    def insert_event(self, event: EventDraft, event_id: str) -> str:
        """Create the event with *our* ID and return it. Safe to call twice with the same ID.

        Google refuses a second event with an ID that already exists (409 "duplicate"). The
        only way that happens here is a retry of an attempt that actually succeeded, so that
        refusal means the event is already in the calendar - which is exactly the goal.
        """
        body = build_event_body(event) | {"id": event_id}
        try:
            created = self._service.events().insert(calendarId="primary", body=body).execute()
        except HttpError as e:
            if is_duplicate_id_error(e):
                return event_id
            if e.status_code == 401:
                raise GoogleAuthError(
                    "Google rejected the saved sign-in - reconnect Google Calendar and sync again"
                ) from e
            raise GoogleCalendarError(f"Google Calendar rejected this event ({e.status_code}: {e.reason})") from e
        return created["id"]


