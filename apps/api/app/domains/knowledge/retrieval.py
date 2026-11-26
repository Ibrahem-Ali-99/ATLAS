import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.knowledge.models import Chunk, Document
from app.domains.knowledge.vectors import (
    index_identity,
    lock_embedding_index,
    model_clause,
    vector_column,
)
from app.integrations.language import EmbeddingClient, OpenAICompatibleEmbeddingClient
from app.integrations.resolver import resolve_settings

# Candidates may sit as far as ATLAS_MAX_COSINE_DISTANCE (0.55).
# A vector-only hit is evidence only at or below this distance.
# nomic-embed-text paraphrases with no shared words measured 0.37–0.43.
# An unsupported address question measured 0.48 against the same passage.
# Full-text matches stay citable past this line, including an exact code at 0.47.
VECTOR_ONLY_MAX_DISTANCE = 0.45


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    page_number: int | None
    content: str
    score: float
    confidence: float


@dataclass
class _Candidate:
    chunk: Chunk
    title: str
    score: float
    distance: float | None
    lexical: bool
    shared_terms: int = 0


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
    settings = (
        embedder.settings
        if isinstance(embedder, OpenAICompatibleEmbeddingClient)
        else get_settings()
    )
    lock_embedding_index(db, organization_id, shared=True)
    use_vectors = True
    if isinstance(embedder, OpenAICompatibleEmbeddingClient):
        try:
            current = resolve_settings(db, organization_id, "embedding")
            use_vectors = index_identity(current) == index_identity(settings)
        except AppError:
            use_vectors = False
    column = vector_column(settings.embedding_dimensions)
    distance = column.cosine_distance(vector)
    vector_rows = (
        db.execute(
            select(Chunk, Document.title, distance.label("distance"))
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.organization_id == organization_id,
                Document.status == "ready",
                Document.archived_at.is_(None),
                column.is_not(None),
                model_clause(settings),
            )
            .order_by(distance.asc())
            .limit(20)
        ).all()
        if use_vectors
        else []
    )
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.search_vector, tsquery)
    text_rows = db.execute(
        select(Chunk, Document.title, rank.label("rank"))
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.organization_id == organization_id,
            Document.status == "ready",
            Document.archived_at.is_(None),
            Chunk.search_vector.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(20)
    ).all()
    fused: dict[uuid.UUID, _Candidate] = {}
    _fuse_vector(fused, vector_rows, settings.max_cosine_distance)
    _fuse_text(fused, text_rows)
    _mark_shared_terms(fused, query)
    ranked = sorted(fused.values(), key=lambda item: item.score, reverse=True)
    evidence = [
        item for item in ranked if _is_evidence(item, settings.rag_vector_only_max_distance)
    ]
    from app.domains.observability.tracing import record_operation

    record_operation(
        operation="retrieval",
        status="succeeded",
        organization_id=organization_id,
        detail={
            "count": len(evidence[:limit]),
            "sources": [
                {"document_id": str(item.chunk.document_id), "score": item.score}
                for item in evidence[:limit]
            ],
            "reason": None if evidence else "no_relevant_evidence",
        },
    )
    return [_record(item) for item in evidence[:limit]]


_CONTENT_TERMS = re.compile(r"[a-z0-9]+")
_SHARED_TERM_STOP_WORDS = {
    "what",
    "when",
    "where",
    "which",
    "about",
    "with",
    "from",
    "that",
    "this",
    "have",
    "does",
    "your",
    "their",
    "into",
    "only",
}


def _mark_shared_terms(fused: dict[uuid.UUID, _Candidate], query: str) -> None:
    """A full-text query requires every word. One shared content word is still evidence.

    "What cold storage services does Harbor offer?" does not match a passage that
    lacks "services" and "offer", even though cold storage is the subject.
    """

    query_terms = _content_terms(query)
    if not query_terms:
        return
    for candidate in fused.values():
        candidate.shared_terms = len(query_terms & _content_terms(candidate.chunk.content))


def _content_terms(text: str) -> set[str]:
    return {
        word
        for word in _CONTENT_TERMS.findall(text.lower())
        if len(word) >= 4 and word not in _SHARED_TERM_STOP_WORDS
    }


def _is_evidence(candidate: _Candidate, vector_threshold: float = VECTOR_ONLY_MAX_DISTANCE) -> bool:
    """A neighbor is not evidence unless the words overlap or the vectors are close.

    Rank position alone is not enough. The nearest passage in a small index can
    still be about a different subject.
    """

    if candidate.lexical or candidate.shared_terms:
        return True
    return candidate.distance is not None and candidate.distance <= vector_threshold


def _fuse_vector(
    fused: dict[uuid.UUID, _Candidate], rows: Sequence[Any], max_distance: float
) -> None:
    for position, row in enumerate(rows, start=1):
        chunk = cast(Chunk, row[0])
        if float(row[2]) > max_distance:
            continue
        _add(fused, chunk, str(row[1]), 1 / (60 + position), distance=float(row[2]), lexical=False)


def _fuse_text(fused: dict[uuid.UUID, _Candidate], rows: Sequence[Any]) -> None:
    for position, row in enumerate(rows, start=1):
        chunk = cast(Chunk, row[0])
        _add(fused, chunk, str(row[1]), 1 / (60 + position), distance=None, lexical=True)


def _add(
    fused: dict[uuid.UUID, _Candidate],
    chunk: Chunk,
    title: str,
    score: float,
    *,
    distance: float | None,
    lexical: bool,
) -> None:
    current = fused.get(chunk.id)
    if current is None:
        fused[chunk.id] = _Candidate(
            chunk=chunk,
            title=title,
            score=score,
            distance=distance,
            lexical=lexical,
        )
        return
    current.score += score
    current.lexical = current.lexical or lexical
    if distance is not None:
        current.distance = distance


def _record(candidate: _Candidate) -> RetrievedChunk:
    chunk = candidate.chunk
    similarity = 1.0 - candidate.distance if candidate.distance is not None else 0.0
    lexical_confidence = 0.85 if candidate.lexical else 0.6 if candidate.shared_terms >= 2 else 0.0
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        document_title=candidate.title,
        chunk_index=chunk.chunk_index,
        page_number=chunk.page_number,
        content=chunk.content,
        score=candidate.score,
        confidence=max(0.0, min(1.0, max(similarity, lexical_confidence))),
    )
