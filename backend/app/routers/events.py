"""GET /events/preview (editing and syncing routes are added in step 6b)"""

from fastapi import APIRouter, Depends

from app.dependencies import get_upload_service
from app.schemas import EventOut
from app.services.upload_service import UploadService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/preview", response_model=list[EventOut])
def preview_events(upload_id: int, service: UploadService = Depends(get_upload_service)):
    return service.get_events(upload_id)
