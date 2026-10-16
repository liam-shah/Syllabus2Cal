"""POST /uploads, GET /uploads/{upload_id}

Routers only deal with HTTP: reading the request and returning a response.
The workflow itself lives in UploadService.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import sessionmaker

from app.dependencies import get_session_factory, get_upload_service
from app.schemas import UploadOut
from app.services.upload_service import UploadService, extract_in_background

router = APIRouter(tags=["uploads"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def read_limited(file: UploadFile) -> bytes:
    # Reading one byte past the limit tells us the file is too big without reading all of it.
    pdf_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (limit is 10 MB)")
    return pdf_bytes


# 202 Accepted: the upload is saved, but the work isn't finished. The client polls
# GET /uploads/{id} until its status is no longer "processing".
@router.post("/uploads", response_model=UploadOut, status_code=202)
def upload_pdf(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    service: UploadService = Depends(get_upload_service),
    session_factory: sessionmaker = Depends(get_session_factory),
):
    pdf_bytes = read_limited(file)
    upload = service.start_upload(file.filename or "upload.pdf", pdf_bytes)
    # Runs after the response has been sent.
    background_tasks.add_task(extract_in_background, session_factory, upload.id, pdf_bytes)
    return upload


@router.get("/uploads/{upload_id}", response_model=UploadOut)
def get_upload(upload_id: int, service: UploadService = Depends(get_upload_service)):
    return service.get_upload(upload_id)
