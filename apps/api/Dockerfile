# API image. Training, ingestion resume, and workflow recovery run in this process.
# Do not start a second copy of this image as a worker. That would recover the same rows twice.
FROM python:3.12-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS run

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv"

WORKDIR /app

RUN useradd --create-home --uid 10001 atlas \
    && mkdir -p /var/lib/atlas/storage /var/lib/atlas/models

COPY --from=build --chown=atlas:atlas /app/.venv /app/.venv
COPY --chown=atlas:atlas app ./app
COPY --chown=atlas:atlas alembic ./alembic
COPY --chown=atlas:atlas alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/atlas-entrypoint

# Root is required only so a newly mounted volume can be given to uid 10001.
# atlas-entrypoint drops to uid 10001 before migrations and uvicorn.
RUN chmod 755 /usr/local/bin/atlas-entrypoint \
    && chown atlas:atlas /var/lib/atlas /var/lib/atlas/storage /var/lib/atlas/models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=4)"

ENTRYPOINT ["atlas-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
