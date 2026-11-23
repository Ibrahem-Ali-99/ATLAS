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
COPY docker-entrypoint.sh /usr/local/bin/atlas-entrypoint

# Root is required only so a newly mounted volume can be chowned to atlas.
# atlas-entrypoint drops to uid 10001 before migrations and uvicorn.
RUN useradd --create-home --uid 10001 atlas \
    && chmod 755 /usr/local/bin/atlas-entrypoint \
    && mkdir -p /var/lib/atlas/storage /var/lib/atlas/models \
    && chown -R atlas:atlas /app /var/lib/atlas

EXPOSE 8000

ENTRYPOINT ["atlas-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
