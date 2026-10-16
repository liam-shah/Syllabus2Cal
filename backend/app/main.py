"""FastAPI app entry point: wires routers, error handling, and startup together.

Run from backend/ with:
    alembic upgrade head                       (create/update the database first)
    uvicorn app.main:app --reload --port 8000
"""

import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app import session_cookie
from app.config import settings
from app.db import engine, ensure_database_is_up_to_date
from app.errors import (
    AppError,
    ConflictError,
    ExternalServiceError,
    InvalidInputError,
    LimitReachedError,
    NotFoundError,
    NotSignedInError,
)
from app.models import LoginSession
from app.routers import auth, events, upload

# Each kind of error maps to one HTTP status. Errors themselves don't know about HTTP.
ERROR_STATUS_CODES: dict[type[AppError], int] = {
    NotSignedInError: 401,
    NotFoundError: 404,
    InvalidInputError: 400,
    ConflictError: 409,
    LimitReachedError: 429,
    ExternalServiceError: 502,
}


def status_code_for(error: AppError) -> int:
    for error_type, status_code in ERROR_STATUS_CODES.items():
        if isinstance(error, error_type):
            return status_code
    return 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables are created and changed by Alembic migrations, never by the app itself; the app
    # only refuses to start on a database that's behind (instead of failing on the first request).
    ensure_database_is_up_to_date(engine)
    yield


app = FastAPI(title="Calendar PDF Sync", lifespan=lifespan)

# The signed session cookie (see session_cookie.py).
#   httponly (always on): page JavaScript can't read it, so injected scripts can't steal it.
#   same_site="lax": the browser leaves it off requests that other sites trigger in the
#       background (forms, fetch), so another site can't make changes as the user (CSRF).
#   https_only: sent over HTTPS only, once the app is deployed with HTTPS.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie=session_cookie.COOKIE_NAME,
    max_age=int(LoginSession.LIFETIME.total_seconds()),
    same_site="lax",
    https_only=settings.cookies_need_https,
)

# The frontend runs on a different origin (port 5173 locally), so browsers only let its
# JavaScript read our responses if we explicitly allow it. Allow exactly what's used.
# allow_credentials: lets the frontend's requests carry the session cookie. Only safe because
# allow_origins is one specific site, never "*". Added last, so it runs first (outermost):
# even error responses get CORS headers, and the frontend can read their message.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
    # Same {"detail": ...} shape as FastAPI's own HTTPException responses.
    headers = {}
    if isinstance(error, LimitReachedError):
        # The standard way to tell any client (not just ours) when to try again, in seconds.
        headers["Retry-After"] = str(math.ceil(error.retry_after.total_seconds()))
    return JSONResponse(status_code=status_code_for(error), content={"detail": str(error)}, headers=headers)


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(events.router)
