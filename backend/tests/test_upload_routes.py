"""The /uploads routes through the real app (HTTP status codes, headers and response shapes)."""

from datetime import timedelta

from sqlalchemy import select

from app.dependencies import get_extraction_queue, get_upload_service
from app.domain import UploadStatus
from app.integrations.cloud_tasks import QueueError
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


def test_when_deployed_an_upload_is_handed_to_the_queue(client):
    queued: list[int] = []
    app.dependency_overrides[get_extraction_queue] = lambda: queued.append  # a fake Cloud Tasks queue

    with claude_returns(DRAFTS) as mock_extract:
        response = upload(client)

    assert response.status_code == 202
    assert queued == [response.json()["id"]]  # one task, carrying only the upload's id
    mock_extract.assert_not_called()  # the queued task runs Claude, not this request
    assert client.get(f"/uploads/{response.json()['id']}").json()["status"] == "processing"


def test_if_the_queue_refuses_the_upload_is_failed_rather_left_processing(client, db):
    def broken_queue(upload_id: int) -> None:
        raise QueueError("Cloud Tasks refused the task (503)")

    app.dependency_overrides[get_extraction_queue] = lambda: broken_queue

    response = upload(client)

    assert response.status_code == 502
    db.expire_all()
    saved = db.scalars(select(Upload)).one()
    assert saved.status is UploadStatus.FAILED  # otherwise the page would poll it forever
    assert "try again" in saved.error_message


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
