import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.knowledge.models import Chunk, Document
from app.domains.knowledge.vectors import model_clause, vector_column
from app.integrations.language import EmbeddingClient


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    page_number: int | None
    content: str
    score: float


def search_chunks(
    db: Session,
    organization_id: uuid.UUID,
    query_text: str,
    embedder: EmbeddingClient,
    *,
    limit: int = 5,
) -> list[RetrievedChunk]:
    query = query_text.strip()
    if len(query) < 2:
        return []
    vector = embedder.embed([query])[0]
    settings = get_settings()
    column = vector_column(settings.embedding_dimensions)
    distance = column.cosine_distance(vector)
    vector_rows = db.execute(
        select(Chunk, Document.title, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.organization_id == organization_id,
            Document.status == "ready",
            column.is_not(None),
            model_clause(settings),
        )
        .order_by(distance.asc())
        .limit(20)
    ).all()
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.search_vector, tsquery)
    text_rows = db.execute(
        select(Chunk, Document.title, rank.label("rank"))
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.organization_id == organization_id,
            Document.status == "ready",
            Chunk.search_vector.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(20)
    ).all()
    fused: dict[uuid.UUID, RetrievedChunk] = {}
    _fuse_vector(fused, vector_rows, get_settings().max_cosine_distance)
    _fuse_text(fused, text_rows)
    ranked = sorted(fused.values(), key=lambda item: item.score, reverse=True)
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="retrieval",
        status="succeeded",
        organization_id=organization_id,
        detail={"count": len(ranked[:limit])},
    )
    return ranked[:limit]


def _fuse_vector(
    fused: dict[uuid.UUID, RetrievedChunk], rows: Sequence[Any], max_distance: float
) -> None:
    """Ignore distant vector neighbors.

    pgvector cosine distance is 1 - cosine similarity. A full-text match can still
    cite the same chunk when the wording overlaps but the vectors are far apart.
    """

    for position, row in enumerate(rows, start=1):
        chunk = cast(Chunk, row[0])
        title = str(row[1])
        if float(row[2]) > max_distance:
            continue
        score = 1 / (60 + position)
        current = fused.get(chunk.id)
        fused[chunk.id] = _record(chunk, title, (current.score if current else 0) + score)


def _fuse_text(fused: dict[uuid.UUID, RetrievedChunk], rows: Sequence[Any]) -> None:
    for position, row in enumerate(rows, start=1):
        chunk = cast(Chunk, row[0])
        title = str(row[1])
        score = 1 / (60 + position)
        current = fused.get(chunk.id)
        fused[chunk.id] = _record(chunk, title, (current.score if current else 0) + score)


def _record(chunk: Chunk, title: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        document_title=title,
        chunk_index=chunk.chunk_index,
        page_number=chunk.page_number,
        content=chunk.content,
        score=score,
    )
