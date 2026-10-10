"""FastAPI app entry point: wires routers, error handling, and startup together.

Run from backend/ with: uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import models  # noqa: F401 - importing registers the tables on Base
from app.config import settings
from app.db import Base, engine
from app.errors import AppError, ExternalServiceError, InvalidInputError, NotFoundError
from app.routers import auth, events, upload

# Each kind of error maps to one HTTP status. Errors themselves don't know about HTTP.
ERROR_STATUS_CODES: dict[type[AppError], int] = {
    NotFoundError: 404,
    InvalidInputError: 400,
    ExternalServiceError: 502,
}


def status_code_for(error: AppError) -> int:
    for error_type, status_code in ERROR_STATUS_CODES.items():
        if isinstance(error, error_type):
            return status_code
    return 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Calendar PDF Sync", lifespan=lifespan)

# The frontend runs on a different origin (port 5173 locally), so browsers only let its
# JavaScript read our responses if we explicitly allow it. Allow exactly what's used.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
    # Same {"detail": ...} shape as FastAPI's own HTTPException responses.
    return JSONResponse(status_code=status_code_for(error), content={"detail": str(error)})


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(events.router)
