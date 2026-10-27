# The backend image, for Cloud Run. Build from backend/:  docker build -t syllabus2cal-api .
# The same image runs the API service and the `migrate` job (alembic upgrade head).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so code-only changes reuse this (slow) layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

# The app, plus the migrations: the app checks it's on the latest one when it starts.
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Don't run as root inside the container.
RUN useradd --create-home --uid 10001 app
USER app

# Cloud Run says which port to listen on in $PORT. Secrets and settings come from the
# environment (Secret Manager), never from a .env file in the image (see .dockerignore).
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
