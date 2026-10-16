"""POST /internal/extractions/{id}: the route Cloud Tasks calls, through the real app.

Cloud Tasks retries any task that doesn't get a 2xx, so the status codes here are the retry
policy: 200 ran, 204 nothing to do (don't retry), 401 not from our queue, 500 unexpected error.
"""

import pytest

from app.config import settings
from app.dependencies import get_task_token_verifier
from app.domain import UploadStatus
from app.integrations.cloud_tasks import TaskTokenError, verify_task_token
from app.main import app
from app.models import Upload
from app.services.upload_service import UploadService
from tests.test_upload_service import DRAFTS, PDF_BYTES, claude_fails, claude_returns


def accept_only(good_token: str):
    """A stand-in for the Google token check (see test_cloud_tasks.py for the real one)."""
    def verify(token: str) -> None:
        if token != good_token:
            raise TaskTokenError("This request isn't from the extraction queue.")
    return verify


@pytest.fixture
def worker(signed_out_client):
    # Signed out on purpose: Cloud Tasks has no user session, only its token.
    app.dependency_overrides[get_task_token_verifier] = lambda: accept_only("from-cloud-tasks")
    return signed_out_client


@pytest.fixture
def processing(db, user) -> Upload:
    return UploadService(db, user).start_upload("cpsc213.pdf", PDF_BYTES)


def run_task(client, upload_id: int, authorization: str | None = "Bearer from-cloud-tasks"):
    headers = {"Authorization": authorization} if authorization is not None else {}
    return client.post(f"/internal/extractions/{upload_id}", headers=headers)


def assert_untouched(db, upload: Upload) -> None:
    db.expire_all()
    stored = db.get(Upload, upload.id)
    assert (stored.status, stored.extraction_claimed_at) == (UploadStatus.PROCESSING, None)


def test_a_task_from_the_queue_extracts_the_upload(worker, db, processing):
    with claude_returns(DRAFTS):
        response = run_task(worker, processing.id)

    assert response.status_code == 200
    db.expire_all()
    assert db.get(Upload, processing.id).status is UploadStatus.EXTRACTED


def test_a_repeated_task_is_a_204_so_the_queue_stops_retrying(worker, processing):
    with claude_returns(DRAFTS) as claude:
        run_task(worker, processing.id)
        response = run_task(worker, processing.id)

    assert response.status_code == 204
    assert claude.call_count == 1


def test_claude_failing_is_still_a_success_for_the_queue(worker, db, processing):
    # The upload is marked failed for the user; retrying would just fail (and cost) again.
    with claude_fails("reply was cut off"):
        response = run_task(worker, processing.id)

    assert response.status_code == 200
    db.expire_all()
    assert db.get(Upload, processing.id).status is UploadStatus.FAILED


@pytest.mark.parametrize("authorization", [None, "Bearer someone-elses-token", "Basic from-cloud-tasks", "from-cloud-tasks"])
def test_a_request_without_the_queues_token_is_a_401_and_changes_nothing(worker, db, processing, authorization):
    with claude_returns(DRAFTS) as claude:
        response = run_task(worker, processing.id, authorization)

    assert response.status_code == 401
    claude.assert_not_called()
    assert_untouched(db, processing)


def test_the_real_check_expects_this_services_url_and_the_tasks_account(monkeypatch):
    monkeypatch.setattr(settings, "service_url", "https://api-abc123-uw.a.run.app")
    monkeypatch.setattr(settings, "tasks_service_account", "tasks@syllabus2cal.iam.gserviceaccount.com")

    verify = get_task_token_verifier()

    assert verify.func is verify_task_token
    assert verify.keywords == {"audience": "https://api-abc123-uw.a.run.app",
                               "service_account": "tasks@syllabus2cal.iam.gserviceaccount.com"}


def test_the_route_does_not_exist_until_the_queue_is_configured(signed_out_client, db, processing):
    # Locally (SERVICE_URL / TASKS_SERVICE_ACCOUNT unset) uploads use BackgroundTasks instead.
    response = run_task(signed_out_client, processing.id)

    assert response.status_code == 404
    assert_untouched(db, processing)
