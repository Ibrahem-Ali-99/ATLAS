import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Response, UploadFile

from app.domains.crm.service import page_bounds
from app.domains.identity.dependencies import CsrfMember, DbSession, Member
from app.domains.knowledge import service
from app.domains.knowledge.retrieval import search_chunks
from app.domains.knowledge.schemas import ChunkOut, ChunkPage, DocumentOut, DocumentPage
from app.domains.provenance.origin import Origin
from app.integrations.language import EmbeddingClient, get_embedding_client

router = APIRouter(prefix="/organizations/{organization_id}", tags=["knowledge"])


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    member: Member,
    db: DbSession,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DocumentPage:
    items, total = service.list_documents(
        db, member.organization.id, q=q, page=page, page_size=page_size
    )
    safe_page, safe_size = page_bounds(page, page_size)
    return DocumentPage(
        items=[DocumentOut.model_validate(item) for item in items],
        page=safe_page,
        page_size=safe_size,
        total=total,
    )


@router.post("/documents", response_model=DocumentOut, status_code=201)
def upload_document(
    member: CsrfMember,
    db: DbSession,
    background: BackgroundTasks,
    file: UploadFile,
    embedder: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    origin: Annotated[Origin, Form()] = Origin.operational,
) -> DocumentOut:
    payload = file.file.read()
    document = service.store_upload(
        db,
        member.organization.id,
        member.user.id,
        filename=file.filename or "document.txt",
        media_type=file.content_type or "application/octet-stream",
        payload=payload,
        origin=origin,
    )
    background.add_task(service.ingest_document, document.id, embedder)
    return DocumentOut.model_validate(document)


@router.get("/documents/search", response_model=ChunkPage)
def search_documents(
    member: Member,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    q: str = Query(min_length=2, max_length=500),
) -> ChunkPage:
    rows = search_chunks(db, member.organization.id, q, embedder)
    return ChunkPage(
        items=[
            ChunkOut(
                id=row.chunk_id,
                document_id=row.document_id,
                document_title=row.document_title,
                chunk_index=row.chunk_index,
                page_number=row.page_number,
                content=row.content,
                score=row.score,
            )
            for row in rows
        ]
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, member: Member, db: DbSession) -> DocumentOut:
    return DocumentOut.model_validate(service.get_document(db, member.organization.id, document_id))


@router.get("/documents/{document_id}/chunks", response_model=ChunkPage)
def document_chunks(document_id: uuid.UUID, member: Member, db: DbSession) -> ChunkPage:
    document = service.get_document(db, member.organization.id, document_id)
    chunks = service.list_chunk_text(db, member.organization.id, document_id)
    return ChunkPage(
        items=[
            ChunkOut(
                id=chunk.id,
                document_id=chunk.document_id,
                document_title=document.title,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                content=chunk.content,
                score=0,
            )
            for chunk in chunks
        ]
    )


@router.post("/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(
    document_id: uuid.UUID,
    member: CsrfMember,
    db: DbSession,
    background: BackgroundTasks,
    embedder: Annotated[EmbeddingClient, Depends(get_embedding_client)],
) -> DocumentOut:
    document = service.mark_reindex(db, member.organization.id, document_id)
    background.add_task(service.ingest_document, document.id, embedder)
    return DocumentOut.model_validate(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_document(db, member.organization.id, document_id)
    return Response(status_code=204)
