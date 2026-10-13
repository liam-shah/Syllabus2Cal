"""GET /events/preview, PATCH /events/{event_id}, POST /events/sync"""

from fastapi import APIRouter, Depends

from app.dependencies import get_event_service, get_sync_service, get_upload_service
from app.domain import EventUpdate
from app.schemas import EventOut
from app.services.event_service import EventService
from app.services.sync_service import SyncService
from app.services.upload_service import UploadService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/preview", response_model=list[EventOut])
def preview_events(upload_id: int, service: UploadService = Depends(get_upload_service)):
    return service.get_events(upload_id)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(event_id: int, update: EventUpdate, service: EventService = Depends(get_event_service)):
    return service.update_event(event_id, update)


@router.post("/sync", response_model=list[EventOut])
def sync_events(upload_id: int, service: SyncService = Depends(get_sync_service)):
    """Send every ticked, not-yet-synced event in the upload to Google Calendar.

    Safe to call again: already-synced events are skipped and failed ones are retried.
    """
    return service.sync_upload(upload_id)
