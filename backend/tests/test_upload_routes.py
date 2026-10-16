"""The /uploads routes through the real app (HTTP status codes, headers and response shapes)."""

from datetime import timedelta

from app.dependencies import get_upload_service
from app.main import app
from app.models import Upload, utc_now
from app.services.upload_service import UploadLimits, UploadService
from tests.test_upload_service import DRAFTS, PDF_BYTES, claude_returns


def upload(client, content: bytes = PDF_BYTES):
    return client.post("/uploads", files={"file": ("schedule.pdf", content, "application/pdf")})


def limit_uploads_to(db, user, per_day: int) -> None:
    app.dependency_overrides[get_upload_service] = lambda: UploadService(db, user, UploadLimits(per_day=per_day))


def test_an_upload_is_accepted_at_once_and_finished_in_the_background(client):
    with claude_returns(DRAFTS):
        response = upload(client)
        # TestClient runs background tasks before it returns, so the job has finished by now.

    assert response.status_code == 202  # Accepted: saved, but the work wasn't done yet
    assert response.json()["status"] == "processing"
    assert "raw_text" not in response.json()  # never sent back

    finished = client.get(f"/uploads/{response.json()['id']}").json()
    assert finished["status"] == "extracted"
    events = client.get("/events/preview", params={"upload_id": finished["id"]}).json()
    assert {event["title"] for event in events} == {draft.title for draft in DRAFTS}


def test_a_file_that_is_not_a_pdf_is_a_400(client):
    assert upload(client, b"not a pdf").status_code == 400


def test_a_reached_limit_is_a_429_saying_when_to_retry(client, db, user):
    db.add(Upload(user=user, filename="old.pdf", raw_text="...", status="extracted",
                  created_at=utc_now() - timedelta(hours=23)))  # stops counting in an hour
    db.commit()
    limit_uploads_to(db, user, per_day=1)

    with claude_returns(DRAFTS) as mock_extract:
        response = upload(client)

    assert response.status_code == 429
    assert response.json()["detail"] == (
        "You've reached the limit of 1 upload per day. You can upload again in about 1 hour."
    )
    # Retry-After (seconds) is the standard header for "try again later", readable by any client.
    assert 3500 < int(response.headers["retry-after"]) <= 3600
    mock_extract.assert_not_called()
