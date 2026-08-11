FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 POETRY_VIRTUALENVS_CREATE=false
WORKDIR /srv/reliastra
RUN apt-get update && apt-get install -y --no-install-recommends curl gcc libpq-dev && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry==2.1.3
COPY pyproject.toml README.md ./
RUN poetry install --only main --no-interaction --no-ansi \
    && playwright install --with-deps chromium \
    && apt-get purge -y gcc && apt-get autoremove -y
COPY . .
RUN useradd --create-home --uid 10001 relia && chown -R relia:relia /srv/reliastra
USER relia
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
