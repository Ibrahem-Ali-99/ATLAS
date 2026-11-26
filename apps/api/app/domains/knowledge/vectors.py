"""Choose the pgvector column that matches the configured embedding width.

`chunks.embedding` stays `vector(1536)` so existing rows are left in place.
`chunks.embedding_768` stores a 768-wide model such as nomic-embed-text.
A query uses one column and the stored model name. A 1536 row with a null
model is the legacy index and is not compared with a 768 query.
"""

import hashlib
import uuid
from typing import Any

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.integrations.resolver import resolve_settings

OPENAI_WIDTH = 1536
NOMIC_WIDTH = 768
SUPPORTED_WIDTHS = frozenset({OPENAI_WIDTH, NOMIC_WIDTH})


def lock_embedding_index(db: Session, organization_id: uuid.UUID, *, shared: bool = False) -> None:
    key = int.from_bytes(
        hashlib.sha256(b"embedding-index:" + organization_id.bytes).digest()[:8],
        "big",
        signed=True,
    )
    statement = (
        text("SELECT pg_advisory_xact_lock_shared(:key)")
        if shared
        else text("SELECT pg_advisory_xact_lock(:key)")
    )
    db.execute(statement, {"key": key})


def index_identity(settings: Settings) -> tuple[str, str, str, int]:
    return (
        settings.embedding_provider,
        settings.embedding_base_url.rstrip("/"),
        settings.embedding_model,
        settings.embedding_dimensions,
    )


def vector_column(width: int) -> Any:
    if width == NOMIC_WIDTH:
        return Chunk.embedding_768
    if width == OPENAI_WIDTH:
        return Chunk.embedding
    raise AppError(500, "embedding_failed", "This deployment has an unsupported embedding width")


def model_clause(settings: Settings) -> Any:
    if settings.embedding_dimensions == OPENAI_WIDTH:
        return or_(
            Chunk.embedding_model == settings.embedding_model,
            Chunk.embedding_model.is_(None),
        )
    return Chunk.embedding_model == settings.embedding_model


def store_chunk_embedding(chunk: Chunk, vector: list[float], settings: Settings) -> None:
    width = settings.embedding_dimensions
    if len(vector) != width or width not in SUPPORTED_WIDTHS:
        raise AppError(
            502,
            "embedding_dimension_mismatch",
            (
                f"The embedding provider returned {len(vector)} values, "
                f"and this deployment expects {width}."
            ),
        )
    chunk.embedding_model = settings.embedding_model
    if width == NOMIC_WIDTH:
        chunk.embedding_768 = vector
        chunk.embedding = None
        return
    chunk.embedding = vector
    chunk.embedding_768 = None


def incompatible_document_count(
    db: Session,
    organization_id: uuid.UUID,
    settings: Settings | None = None,
) -> int:
    if settings is None:
        try:
            settings = resolve_settings(db, organization_id, "embedding", for_verification=True)
        except AppError:
            settings = get_settings()
    if settings.embedding_provider == "double":
        return 0
    column = vector_column(settings.embedding_dimensions)
    has_current = exists(
        select(Chunk.id).where(
            Chunk.document_id == Document.id,
            Chunk.organization_id == organization_id,
            column.is_not(None),
            model_clause(settings),
        )
    )
    has_chunks = exists(
        select(Chunk.id).where(
            Chunk.document_id == Document.id,
            Chunk.organization_id == organization_id,
        )
    )
    counted = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.organization_id == organization_id,
            Document.status == DocumentStatus.ready,
            has_chunks,
            ~has_current,
        )
    )
    return int(counted or 0)
