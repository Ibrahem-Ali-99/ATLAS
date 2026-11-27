import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
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

# Candidate search stays broad. Answerability is a separate stage.
# Tuned on the Feld development split only. The inspected held-out set and the
# fresh final set must not change this name.
PRODUCTION_PIPELINE = "answerable"

PipelineName = Literal[
    "lexical",
    "dense",
    "baseline",
    "hybrid",
    "hybrid_meta",
    "hybrid_rerank",
    "hybrid_full",
    "answerable",
]


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
    lexical_strict: bool = False


def search_chunks(
    db: Session,
    organization_id: uuid.UUID,
    query_text: str,
    embedder: EmbeddingClient,
    *,
    limit: int = 5,
    pipeline: Literal[
        "lexical",
        "dense",
        "baseline",
        "hybrid",
        "hybrid_meta",
        "hybrid_rerank",
        "hybrid_full",
        "answerable",
    ] = "hybrid",
) -> list[RetrievedChunk]:
    """Retrieve ready chunks for one organization.

    ``lexical`` is full-text only. ``dense`` is the vector-only gate.
    ``baseline`` fuses AND full-text with vector neighbors by reciprocal rank.
    ``hybrid`` adds an OR full-text query. ``hybrid_meta`` adds title filtering.
    ``hybrid_rerank`` replaces reciprocal-rank order with the second-stage score.
    ``hybrid_full`` applies that score, title filtering, and near-duplicate removal.
    ``answerable`` uses the hybrid candidate pool, then keeps passages that
    contain the requested fact.
    """

    query = query_text.strip()
    if len(query) < 2:
        return []
    vector = embedder.embed([query])[0]
    custom = getattr(embedder, "settings", None)
    settings = custom if isinstance(custom, Settings) else get_settings()
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
    text_rows = _text_rows(db, organization_id, tsquery, rank)
    use_or = pipeline in {"hybrid", "hybrid_meta", "hybrid_rerank", "hybrid_full", "answerable"}
    partial_rows: Sequence[Any] = []
    strict_ids = {cast(Chunk, row[0]).id for row in text_rows} if use_or else set()
    if use_or:
        or_query = _or_tsquery(query)
        if or_query is not None:
            or_rank = func.ts_rank_cd(Chunk.search_vector, or_query)
            partial_rows = _text_rows(db, organization_id, or_query, or_rank)
    fused: dict[uuid.UUID, _Candidate] = {}
    if pipeline != "lexical":
        vector_limit = (
            settings.rag_vector_only_max_distance
            if pipeline == "dense"
            else settings.max_cosine_distance
        )
        _fuse_vector(fused, vector_rows, vector_limit)
    if pipeline != "dense":
        _fuse_text(fused, text_rows)
        _fuse_text(fused, partial_rows)
    _mark_shared_terms(fused, query)
    query_terms = _content_terms(query)
    if use_or:
        for candidate in fused.values():
            if candidate.chunk.id in strict_ids:
                candidate.lexical_strict = True
                candidate.lexical = True
    if pipeline == "answerable":
        evidence = _answerable(query, fused, query_terms, limit)
    else:
        evidence = _select_evidence(
            fused, pipeline, query_terms, settings.rag_vector_only_max_distance
        )
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
            "pipeline": pipeline,
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


def _answerable(
    query: str,
    fused: dict[uuid.UUID, _Candidate],
    query_terms: set[str],
    limit: int,
) -> list[_Candidate]:
    from app.domains.knowledge.evidence import PassageView, select_answerable

    ranked = sorted(fused.values(), key=lambda item: _hybrid_rank(item, query_terms), reverse=True)
    views = [
        PassageView(str(item.chunk.id), item.title, item.chunk.content, item.score)
        for item in ranked
    ]
    by_key = {str(item.chunk.id): item for item in ranked}
    chosen = select_answerable(query, views, limit=limit)
    return [by_key[item.key] for item in chosen if item.key in by_key]


def _select_evidence(
    fused: dict[uuid.UUID, _Candidate],
    pipeline: PipelineName,
    query_terms: set[str],
    vector_threshold: float,
) -> list[_Candidate]:
    if pipeline == "dense":
        ranked = sorted(
            fused.values(), key=lambda item: item.distance if item.distance is not None else 2
        )
        return [
            item
            for item in ranked
            if item.distance is not None and item.distance <= vector_threshold
        ]
    if pipeline in {"hybrid_rerank", "hybrid_full"}:
        ranked = sorted(
            fused.values(), key=lambda item: _hybrid_rank(item, query_terms), reverse=True
        )
    else:
        ranked = sorted(fused.values(), key=lambda item: item.score, reverse=True)
    if pipeline == "lexical":
        evidence = [item for item in ranked if item.lexical]
    elif pipeline in {"hybrid", "hybrid_meta", "hybrid_rerank", "hybrid_full"}:
        evidence = [
            item for item in ranked if _is_hybrid_evidence(item, len(query_terms), vector_threshold)
        ]
    else:
        evidence = [item for item in ranked if _is_evidence(item, vector_threshold)]
    if pipeline in {"hybrid_meta", "hybrid_full"}:
        evidence = _filter_by_title(evidence, query_terms)
    if pipeline == "hybrid_full":
        evidence = _drop_near_duplicates(evidence)
    return evidence


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


def _text_rows(db: Session, organization_id: uuid.UUID, tsquery: Any, rank: Any) -> Sequence[Any]:
    return db.execute(
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


def _or_tsquery(query: str) -> Any | None:
    """Match a passage that shares a content word, not every word in the question."""

    terms = sorted(_content_terms(query))
    if len(terms) < 2 or any(not re.fullmatch(r"[a-z0-9]+", term) for term in terms):
        return None
    return func.to_tsquery("english", " | ".join(terms))


def _hybrid_rank(candidate: _Candidate, query_terms: set[str]) -> float:
    count = len(query_terms) or 1
    overlap = candidate.shared_terms / count
    similarity = 0.0 if candidate.distance is None else max(0.0, 1.0 - candidate.distance)
    title_overlap = len(query_terms & _content_terms(candidate.title)) / count
    strict_bonus = 0.25 if candidate.lexical_strict else 0.0
    return candidate.score * 50 + overlap + 0.35 * similarity + 0.2 * title_overlap + strict_bonus


def _is_hybrid_evidence(
    candidate: _Candidate, query_term_count: int, vector_threshold: float
) -> bool:
    """A one-word overlap is evidence when it was already a vector neighbor.

    A partial full-text hit with no nearby vector needs two shared words, or
    half of the question's content words. That keeps "storage" searchable and
    keeps one incidental word from answering a different question.
    """

    partial_only = candidate.lexical and not candidate.lexical_strict and candidate.distance is None
    if partial_only:
        if query_term_count <= 1:
            return candidate.shared_terms > 0
        if query_term_count == 0:
            return False
        return candidate.shared_terms >= 2 or candidate.shared_terms / query_term_count >= 0.5
    return _is_evidence(candidate, vector_threshold)


_GENERIC_TITLE_TERMS = {
    "brochure",
    "card",
    "code",
    "company",
    "customer",
    "document",
    "documents",
    "notice",
    "policy",
    "public",
    "rate",
    "rates",
    "service",
    "services",
    "storage",
    "warehouse",
    "warehousing",
    "yard",
}


def _filter_by_title(evidence: list[_Candidate], query_terms: set[str]) -> list[_Candidate]:
    """Keep one document when the question names its title and no other title."""

    distinctive = {
        term for term in query_terms if len(term) >= 5 and term not in _GENERIC_TITLE_TERMS
    }
    if not distinctive:
        return evidence
    matched: set[str] = set()
    for item in evidence:
        if distinctive & _content_terms(item.title):
            matched.add(item.title)
    if len(matched) != 1:
        return evidence
    title = next(iter(matched))
    filtered = [item for item in evidence if item.title == title]
    return filtered or evidence


def _drop_near_duplicates(evidence: list[_Candidate]) -> list[_Candidate]:
    kept: list[_Candidate] = []
    kept_terms: list[set[str]] = []
    for item in evidence:
        terms = _content_terms(item.chunk.content)
        duplicate = False
        for prior, prior_terms in zip(kept, kept_terms, strict=True):
            if prior.chunk.document_id != item.chunk.document_id:
                continue
            union = terms | prior_terms
            if union and len(terms & prior_terms) / len(union) >= 0.85:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
            kept_terms.append(terms)
    return kept


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
