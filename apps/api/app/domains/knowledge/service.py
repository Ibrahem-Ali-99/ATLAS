import uuid
from pathlib import Path

import structlog
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.knowledge.chunking import chunk_pages
from app.domains.knowledge.extract import extract_text
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.integrations.language import EmbeddingClient, get_embedding_client

logger = structlog.get_logger(__name__)
ALLOWED_TYPES = {"application/pdf", "text/plain", "application/octet-stream"}


def list_documents(
    db: Session, organization_id: uuid.UUID, *, q: str | None, page: int, page_size: int
) -> tuple[list[Document], int]:
    from app.domains.crm.service import page_bounds

    safe_page, safe_size = page_bounds(page, page_size)
    query = select(Document).where(Document.organization_id == organization_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(or_(Document.title.ilike(term), Document.filename.ilike(term)))
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(
        query.order_by(Document.created_at.desc())
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
    )
    db.add(document)
    db.flush()
    path = _storage_path(organization_id, document.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    document.storage_path = str(path)
    db.commit()
    db.refresh(document)
    return document


def delete_document(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> None:
    document = get_document(db, organization_id, document_id)
    path = Path(document.storage_path)
    db.delete(document)
    db.commit()
    _unlink_stored(path)


def mark_reindex(db: Session, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = get_document(db, organization_id, document_id)
    document.status = DocumentStatus.pending
    document.error_message = None
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
    for document_id in document_ids:
        ingest_document(document_id, embedder)
    return len(document_ids)


def ingest_document(document_id: uuid.UUID, embedder: EmbeddingClient | None = None) -> None:
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
        client = embedder or get_embedding_client()
        vectors = client.embed([piece.content for piece in pieces])
        if len(vectors) != len(pieces) or any(
            len(vector) != get_settings().embedding_dimensions for vector in vectors
        ):
            _record_failure(db, document, "The embedding provider returned an unexpected response")
            return
        db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        for piece, vector in zip(pieces, vectors, strict=True):
            db.add(
                Chunk(
                    organization_id=document.organization_id,
                    document_id=document.id,
                    chunk_index=piece.index,
                    page_number=piece.page_number,
                    content=piece.content,
                    embedding=vector,
                )
            )
        db.flush()
        db.execute(
            update(Chunk)
            .where(Chunk.document_id == document.id)
            .values(search_vector=func.to_tsvector("english", Chunk.content))
        )
        document.status = DocumentStatus.ready
        document.error_message = None
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
