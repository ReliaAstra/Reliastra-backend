FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main \
    || pip install --no-cache-dir fastapi uvicorn "sqlalchemy[asyncio]" asyncpg alembic pydantic pydantic-settings celery redis httpx jinja2 playwright xhtml2pdf pyjwt bcrypt cryptography minio email-validator python-multipart

RUN playwright install --with-deps chromium || true

COPY . /app/

CMD ["celery", "-A", "app.infrastructure.celery_app.celery_app", "worker", "--loglevel=info"]
