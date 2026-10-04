"""POST /uploads, GET /uploads/{upload_id}

Routers only deal with HTTP: reading the request and returning a response.
The workflow itself lives in UploadService.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.dependencies import get_upload_service
from app.schemas import UploadOut
from app.services.upload_service import UploadService

router = APIRouter(tags=["uploads"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def read_limited(file: UploadFile) -> bytes:
    # Reading one byte past the limit tells us the file is too big without reading all of it.
    pdf_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF is too large (limit is 10 MB)")
    return pdf_bytes


@router.post("/uploads", response_model=UploadOut, status_code=201)
def upload_pdf(file: UploadFile, service: UploadService = Depends(get_upload_service)):
    return service.process_pdf(file.filename or "upload.pdf", read_limited(file))


@router.get("/uploads/{upload_id}", response_model=UploadOut)
def get_upload(upload_id: int, service: UploadService = Depends(get_upload_service)):
    return service.get_upload(upload_id)
