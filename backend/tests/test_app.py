"""App-wide behaviour set up in main.py: CORS and the central error handler."""

import pytest

from app.config import settings
from app.errors import AppError, NotFoundError
from app.integrations.google_calendar import GoogleCalendarError
from app.integrations.llm_extraction import LLMExtractionError
from app.integrations.pdf_extraction import PDFExtractionError
from app.main import status_code_for

FRONTEND = settings.frontend_url
SOME_OTHER_SITE = "https://evil.example.com"


def preflight(client, origin: str, method: str = "PATCH"):
    # What a browser sends before a cross-origin PATCH or JSON POST.
    return client.options("/events/preview", headers={
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "content-type",
    })


def test_preflight_from_the_frontend_is_allowed(client):
    response = preflight(client, FRONTEND)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_preflight_from_another_site_is_refused(client):
    response = preflight(client, SOME_OTHER_SITE)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_unused_methods_are_not_allowed(client):
    assert preflight(client, FRONTEND, method="DELETE").status_code == 400


def test_responses_only_grant_read_access_to_the_frontend(client):
    allowed = client.get("/auth/google/status", headers={"Origin": FRONTEND})
    other = client.get("/auth/google/status", headers={"Origin": SOME_OTHER_SITE})
    assert allowed.headers["access-control-allow-origin"] == FRONTEND
    # The request still runs (CORS is enforced by the browser), but without this header
    # the other site's JavaScript isn't allowed to read the response.
    assert "access-control-allow-origin" not in other.headers


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (NotFoundError("x"), 404),
        (PDFExtractionError("x"), 400),
        (LLMExtractionError("x"), 502),
        (GoogleCalendarError("x"), 502),
        (AppError("x"), 500),  # an AppError with no category mapped is visible, not hidden
    ],
)
def test_each_error_category_maps_to_one_status_code(error, status_code):
    assert status_code_for(error) == status_code


def test_errors_reach_the_client_as_json_detail(client):
    response = client.get("/uploads/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Upload not found"}
