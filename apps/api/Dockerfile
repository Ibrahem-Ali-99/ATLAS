# API image. Training, ingestion resume, and workflow recovery run in this process.
# Do not start a second copy of this image as a worker. That would recover the same rows twice.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home --uid 10001 atlas \
    && chown -R atlas:atlas /app
USER atlas

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
