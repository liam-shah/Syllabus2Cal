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
REDIRECT_URI = "http://localhost:8000/auth/google/callback"
TIMEZONE = "America/Vancouver"


class GoogleCalendarError(ExternalServiceError):
    """Raised when signing in to Google or creating a calendar event fails."""


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
            raise GoogleCalendarError(
                "Google access expired or was revoked - reconnect your Google account"
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


def insert_event(credentials: Credentials, event: EventDraft) -> str:
    service = build("calendar", "v3", credentials=credentials)
    try:
        created = service.events().insert(
            calendarId="primary", body=build_event_body(event)
        ).execute()
    except HttpError as e:
        raise GoogleCalendarError(f"Google Calendar rejected the event '{event.title}': {e}") from e
    return created["id"]


