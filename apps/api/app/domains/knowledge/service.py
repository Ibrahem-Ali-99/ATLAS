import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.knowledge.chunking import chunk_pages
from app.domains.knowledge.extract import extract_text
from app.domains.knowledge.models import (
    Chunk,
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionJobStatus,
)
from app.domains.knowledge.vectors import (
    index_identity,
    lock_embedding_index,
    store_chunk_embedding,
)
from app.domains.provenance.origin import Origin
from app.integrations.language import EmbeddingClient, get_embedding_client
from app.integrations.resolver import resolve_settings

logger = structlog.get_logger(__name__)
ALLOWED_TYPES = {"application/pdf", "text/plain", "application/octet-stream"}


def list_documents(
    db: Session,
    organization_id: uuid.UUID,
    *,
    q: str | None,
    page: int,
    page_size: int,
    status: DocumentStatus | None = None,
    file_type: str | None = None,
) -> tuple[list[Document], int]:
    from app.domains.crm.service import page_bounds

    safe_page, safe_size = page_bounds(page, page_size)
    query = select(Document).where(Document.organization_id == organization_id)
    if q and q.strip():
        term = q.strip()
        query = query.where(
            or_(
                Document.title.icontains(term, autoescape=True),
                Document.filename.icontains(term, autoescape=True),
            )
        )
    if status is not None:
        query = query.where(Document.status == status)
    if file_type is not None:
        query = query.where(
            func.lower(Document.filename).endswith(f".{file_type}", autoescape=True)
        )
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(
        query.order_by(Document.created_at.desc(), Document.id.desc())
        .offset((safe_page - 1) * safe_size)
        .limit(safe_size)
    ).all()
    return list(rows), int(total)


def get_document(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id, Document.organization_id == organization_id
        )
    )
    if document is None:
        raise AppError(404, "not_found", "Resource not found")
    return document


def store_upload(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    filename: str,
    media_type: str,
    payload: bytes,
    origin: Origin = Origin.operational,
) -> Document:
    settings = get_settings()
    safe_name = Path(filename).name.strip()
    if not safe_name or not (
        safe_name.lower().endswith(".pdf") or safe_name.lower().endswith(".txt")
    ):
        raise AppError(415, "unsupported_media", "Only PDF and TXT documents can be uploaded")
    normalized_type = media_type.split(";", 1)[0].strip().lower()
    if normalized_type not in ALLOWED_TYPES:
        raise AppError(415, "unsupported_media", "Only PDF and TXT documents can be uploaded")
    if not payload:
        raise AppError(422, "invalid_document", "The document is empty")
    if len(payload) > settings.max_upload_bytes:
        raise AppError(413, "document_too_large", "The document exceeds the upload size limit")
    extract_text(safe_name, payload)
    document = Document(
        organization_id=organization_id,
        uploaded_by=user_id,
        title=Path(safe_name).stem[:200] or safe_name[:200],
        filename=safe_name[:255],
        media_type="application/pdf" if safe_name.lower().endswith(".pdf") else "text/plain",
        byte_size=len(payload),
        storage_path="",
        status=DocumentStatus.pending,
        origin=origin,
    )
    db.add(document)
    db.flush()
    path = _storage_path(organization_id, document.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    document.storage_path = str(path)
    db.add(
        IngestionJob(
            organization_id=organization_id,
            document_id=document.id,
            idempotency_key=f"document:{document.id}:v1",
        )
    )
    db.commit()
    db.refresh(document)
    return document


def delete_document(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> None:
    lock_embedding_index(db, organization_id)
    document = get_document(db, organization_id, document_id)
    path = Path(document.storage_path)
    db.execute(delete(IngestionJob).where(IngestionJob.document_id == document.id))
    db.delete(document)
    db.commit()
    _unlink_stored(path)


def mark_reindex(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = get_document(db, organization_id, document_id)
    document.status = DocumentStatus.pending
    document.error_message = None
    existing = db.scalar(select(IngestionJob).where(IngestionJob.document_id == document.id))
    if existing is None:
        db.add(
            IngestionJob(
                organization_id=organization_id,
                document_id=document.id,
                idempotency_key=f"document:{document.id}:v1",
            )
        )
    else:
        existing.status = IngestionJobStatus.queued
        existing.attempts = 0
        existing.next_attempt_at = datetime.now(UTC)
        existing.error_message = None
        existing.lease_owner = None
        existing.lease_expires_at = None
    db.commit()
    db.refresh(document)
    return document


def list_chunk_text(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> list[Chunk]:
    get_document(db, organization_id, document_id)
    return list(
        db.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id, Chunk.organization_id == organization_id)
            .order_by(Chunk.chunk_index.asc())
        ).all()
    )


def resume_incomplete_documents(embedder: EmbeddingClient | None = None) -> int:
    """Index documents still pending or processing after a restart.

    Chunks are replaced in the same transaction as the ready status, so a repeated
    run does not leave two copies of the same passage.
    """

    db = SessionLocal()
    try:
        document_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.status.in_([DocumentStatus.pending, DocumentStatus.processing])
                )
            ).all()
        )
    finally:
        db.close()
    db = SessionLocal()
    try:
        for document_id in document_ids:
            document = db.get(Document, document_id)
            if document is None:
                continue
            existing = db.scalar(
                select(IngestionJob).where(IngestionJob.document_id == document_id)
            )
            if existing is None:
                db.add(
                    IngestionJob(
                        organization_id=document.organization_id,
                        document_id=document_id,
                        idempotency_key=f"document:{document_id}:v1",
                    )
                )
            elif existing.status in {
                IngestionJobStatus.succeeded,
                IngestionJobStatus.failed,
            }:
                existing.status = IngestionJobStatus.queued
                existing.next_attempt_at = datetime.now(UTC)
                existing.error_message = None
                existing.lease_owner = None
                existing.lease_expires_at = None
            elif (
                existing.status == IngestionJobStatus.running
                and existing.lease_expires_at is not None
                and existing.lease_expires_at < datetime.now(UTC)
            ):
                existing.status = IngestionJobStatus.retrying
                existing.lease_owner = None
                existing.lease_expires_at = None
                existing.next_attempt_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
    return len(document_ids)


def claim_ingestion_job(worker_id: str, lease_seconds: int = 60) -> IngestionJob | None:
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        job = db.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.status.in_(
                    [
                        IngestionJobStatus.queued,
                        IngestionJobStatus.retrying,
                        IngestionJobStatus.running,
                    ]
                ),
                IngestionJob.next_attempt_at <= now,
                (IngestionJob.lease_expires_at.is_(None) | (IngestionJob.lease_expires_at < now)),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            db.rollback()
            return None
        job.status = IngestionJobStatus.running
        job.attempts += 1
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at = now
        db.commit()
        db.refresh(job)
        return job
    finally:
        db.close()


def retry_ingestion_job(
    db: Session, organization_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = get_document(db, organization_id, document_id)
    job = db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.document_id == document.id,
            IngestionJob.organization_id == organization_id,
        )
        .with_for_update()
    )
    if job is None:
        raise AppError(404, "ingestion_job_not_found", "No ingestion job exists for this document")
    if job.status not in {IngestionJobStatus.failed, IngestionJobStatus.retrying}:
        raise AppError(
            409,
            "ingestion_retry_not_allowed",
            "This ingestion job is not eligible for retry",
        )
    job.status = IngestionJobStatus.queued
    job.next_attempt_at = datetime.now(UTC)
    job.error_message = None
    job.lease_owner = None
    job.lease_expires_at = None
    document.status = DocumentStatus.pending
    document.error_message = None
    db.commit()
    db.refresh(document)
    return document


def run_ingestion_job(
    job: IngestionJob, worker_id: str, embedder: EmbeddingClient | None = None
) -> None:
    ingest_document(job.document_id, embedder, job_id=job.id, worker_id=worker_id)
    db = SessionLocal()
    try:
        document = db.get(Document, job.document_id)
        current = db.get(IngestionJob, job.id)
        if current is None:
            return
        now = datetime.now(UTC)
        owns_lease = db.scalar(
            select(IngestionJob.id).where(
                IngestionJob.id == job.id,
                IngestionJob.status == IngestionJobStatus.running,
                IngestionJob.lease_owner == worker_id,
                IngestionJob.lease_expires_at > now,
            )
        )
        if owns_lease is None:
            logger.warning("knowledge_ingestion_stale_completion", job_id=str(job.id))
            db.rollback()
            return
        current.lease_owner = None
        current.lease_expires_at = None
        current.heartbeat_at = now
        if document is not None and document.status == DocumentStatus.ready:
            current.status = IngestionJobStatus.succeeded
            current.error_message = None
        else:
            current.error_message = (
                document.error_message
                if document and document.error_message
                else "Document was removed"
            )[:500]
            current.status = (
                IngestionJobStatus.failed
                if current.attempts >= current.max_attempts
                else IngestionJobStatus.retrying
            )
            current.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=min(300, 2**current.attempts)
            )
        db.commit()
    finally:
        db.close()


def ingest_document(
    document_id: uuid.UUID,
    embedder: EmbeddingClient | None = None,
    *,
    job_id: uuid.UUID | None = None,
    worker_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.status = DocumentStatus.processing
        document.error_message = None
        db.commit()
        stored = _stored_file(document.storage_path)
        if stored is None:
            _record_failure(db, document, "The stored document could not be read")
            return
        payload = stored.read_bytes()
        pages = extract_text(document.filename, payload)
        try:
            pieces = chunk_pages(pages)
        except ValueError:
            _record_failure(db, document, "Document is too long to index")
            return
        if not pieces:
            _record_failure(db, document, "No text could be extracted from the document")
            return
        resolved = resolve_settings(db, document.organization_id, "embedding")
        client = embedder or get_embedding_client(db, document.organization_id)
        vectors = client.embed([piece.content for piece in pieces])
        if len(vectors) != len(pieces) or any(
            len(vector) != resolved.embedding_dimensions for vector in vectors
        ):
            _record_failure(db, document, "The embedding provider returned an unexpected response")
            return
        lock_embedding_index(db, document.organization_id)
        db.expire_all()
        current = resolve_settings(db, document.organization_id, "embedding")
        if index_identity(current) != index_identity(resolved):
            raise AppError(
                409,
                "embedding_model_changed",
                "The workspace index changed during ingestion. Retry this document.",
            )
        db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        for piece, vector in zip(pieces, vectors, strict=True):
            chunk = Chunk(
                organization_id=document.organization_id,
                document_id=document.id,
                chunk_index=piece.index,
                page_number=piece.page_number,
                content=piece.content,
            )
            store_chunk_embedding(chunk, vector, resolved)
            db.add(chunk)
        db.flush()
        db.execute(
            update(Chunk)
            .where(Chunk.document_id == document.id)
            .values(search_vector=func.to_tsvector("english", Chunk.content))
        )
        document.status = DocumentStatus.ready
        document.error_message = None
        if job_id is not None and worker_id is not None:
            lease_ok = db.scalar(
                select(IngestionJob.id).where(
                    IngestionJob.id == job_id,
                    IngestionJob.status == IngestionJobStatus.running,
                    IngestionJob.lease_owner == worker_id,
                    IngestionJob.lease_expires_at > datetime.now(UTC),
                )
            )
            if lease_ok is None:
                db.rollback()
                logger.warning("knowledge_ingestion_lease_lost", job_id=str(job_id))
                return
        db.commit()
    except AppError as exc:
        db.rollback()
        _fail_existing(db, document_id, exc.message)
    except Exception:
        logger.error("document_ingest_failed", document_id=str(document_id))
        db.rollback()
        _fail_existing(db, document_id, "Document processing failed")
    finally:
        db.close()


def _record_failure(db: Session, document: Document, message: str) -> None:
    indexed = (
        db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id))
        or 0
    )
    document.status = DocumentStatus.ready if indexed else DocumentStatus.failed
    document.error_message = message[:500]
    db.commit()


def _fail_existing(db: Session, document_id: uuid.UUID, message: str) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return
    _record_failure(db, document, message)


def _storage_path(organization_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    root = get_settings().upload_storage_dir.resolve()
    path = (root / str(organization_id) / str(document_id)).resolve()
    if not path.is_relative_to(root):
        raise AppError(422, "invalid_document", "The document path is not allowed")
    return path


def _stored_file(storage_path: str) -> Path | None:
    if not storage_path:
        return None
    root = get_settings().upload_storage_dir.resolve()
    path = Path(storage_path).resolve()
    if not path.is_file() or not path.is_relative_to(root):
        return None
    return path


def _unlink_stored(path: Path) -> None:
    stored = _stored_file(str(path))
    if stored is not None:
        stored.unlink()
