"""GET /events/preview, PATCH /events/{event_id} (syncing comes in slice 3)"""

from fastapi import APIRouter, Depends

from app.dependencies import get_event_service, get_upload_service
from app.domain import EventUpdate
from app.schemas import EventOut
from app.services.event_service import EventService
from app.services.upload_service import UploadService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/preview", response_model=list[EventOut])
def preview_events(upload_id: int, service: UploadService = Depends(get_upload_service)):
    return service.get_events(upload_id)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(event_id: int, update: EventUpdate, service: EventService = Depends(get_event_service)):
    return service.update_event(event_id, update)
