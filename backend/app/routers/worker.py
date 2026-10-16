"""POST /internal/extractions/{upload_id}: the route Cloud Tasks calls to run an extraction.

Cloud Tasks retries any task that doesn't get a 2xx, so these responses are the retry policy:
  200  the extraction ran (even if Claude failed: the upload is marked failed, and a retry
       would only fail - and cost - again)
  204  nothing to do: already claimed by another run, or no longer processing. Don't retry.
  401  not from our queue (require_cloud_tasks), before anything is touched
  500  something unexpected: the upload is marked failed, and a retry finds it claimed (204)
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import sessionmaker

from app.dependencies import get_session_factory, require_cloud_tasks
from app.services.upload_service import run_extraction

router = APIRouter(prefix="/internal", dependencies=[Depends(require_cloud_tasks)], include_in_schema=False)


@router.post("/extractions/{upload_id}")
def run_extraction_task(upload_id: int, session_factory: sessionmaker = Depends(get_session_factory)):
    ran = run_extraction(session_factory, upload_id)
    return Response(status_code=200 if ran else 204)
