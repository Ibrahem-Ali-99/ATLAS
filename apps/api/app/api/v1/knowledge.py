# ruff: noqa: E501
import uuid
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from sqlalchemy import select

from app.api.v1.inbox import evaluate_inbox_draft
from app.core.errors import AppError
from app.domains.assistant.service import evaluate_response
from app.domains.billing.service import enforce_limit
from app.domains.crm.service import page_bounds
from app.domains.demo.access import MAX_UPLOAD_BYTES, is_visitor_slug
from app.domains.demo.service import enforce_demo_upload
from app.domains.identity.dependencies import Admin, CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.knowledge import reindex, service
from app.domains.knowledge.models import (
    DocumentStatus,
    EvaluationQuestion,
    EvaluationRun,
    IngestionJob,
)
from app.domains.knowledge.retrieval import search_chunks
from app.domains.knowledge.schemas import (
    ChunkOut,
    ChunkPage,
    DocumentOut,
    DocumentPage,
    DocumentPreview,
    EvaluationQuestionCreate,
    EvaluationQuestionOut,
    EvaluationRunOut,
)
from app.domains.provenance.origin import Origin
from app.integrations.language import (
    ChatClient,
    EmbeddingClient,
    get_chat_client,
    get_embedding_client,
)

router = APIRouter(prefix="/organizations/{organization_id}", tags=["knowledge"])


@router.get("/knowledge/embedding-reindex")
def embedding_reindex_status(admin: Admin, db: DbSession) -> dict[str, object] | None:
    return reindex.progress(db, admin.organization.id)


@router.post("/knowledge/embedding-reindex", status_code=202)
def start_embedding_reindex(
    body: reindex.ReindexRequest, admin: CsrfAdmin, db: DbSession
) -> dict[str, object] | None:
    reindex.start(db, admin.organization.id, admin.user.id, body)
    return reindex.progress(db, admin.organization.id)


@router.delete("/knowledge/embedding-reindex", status_code=204)
def cancel_embedding_reindex(admin: CsrfAdmin, db: DbSession) -> None:
    reindex.cancel(db, admin.organization.id)


def organization_embedder(request: Request, member: Member, db: DbSession) -> EmbeddingClient:
    override = request.app.dependency_overrides.get(get_embedding_client)
    if override is not None:
        return cast(EmbeddingClient, override())
    return get_embedding_client(db, member.organization.id)


def organization_chat(request: Request, member: Member, db: DbSession) -> ChatClient:
    override = request.app.dependency_overrides.get(get_chat_client)
    if override is not None:
        return cast(ChatClient, override())
    return get_chat_client(db, member.organization.id)


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    member: Member,
    db: DbSession,
    q: str | None = None,
    status: DocumentStatus | None = None,
    file_type: Literal["pdf", "txt"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = False,
) -> DocumentPage:
    items, total = service.list_documents(
        db,
        member.organization.id,
        q=q,
        page=page,
        page_size=page_size,
        status=status,
        file_type=file_type,
        include_archived=include_archived,
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
    file: UploadFile,
    origin: Annotated[Origin, Form()] = Origin.operational,
) -> DocumentOut:
    if is_visitor_slug(member.organization.slug):
        payload = file.file.read(MAX_UPLOAD_BYTES + 1)
    else:
        payload = file.file.read()
    enforce_demo_upload(db, member.organization, len(payload))
    enforce_limit(db, member.organization.id, "knowledge_storage_bytes", len(payload))
    document = service.store_upload(
        db,
        member.organization.id,
        member.user.id,
        filename=file.filename or "document.txt",
        media_type=file.content_type or "application/octet-stream",
        payload=payload,
        origin=origin,
    )
    return DocumentOut.model_validate(document)


@router.get("/documents/{document_id}/job")
def document_job(document_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, object]:
    service.get_document(db, member.organization.id, document_id)
    job = db.scalar(
        select(IngestionJob).where(
            IngestionJob.document_id == document_id,
            IngestionJob.organization_id == member.organization.id,
        )
    )
    if job is None:
        return {"status": "unavailable"}
    return {
        "id": str(job.id),
        "document_id": str(job.document_id),
        "status": job.status.value,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.post("/documents/{document_id}/job/retry", response_model=DocumentOut)
def retry_document_job(document_id: uuid.UUID, admin: CsrfAdmin, db: DbSession) -> DocumentOut:
    return DocumentOut.model_validate(
        service.retry_ingestion_job(db, admin.organization.id, document_id)
    )


@router.get("/documents/search", response_model=ChunkPage)
def search_documents(
    member: Member,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(organization_embedder)],
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


@router.get("/knowledge/evaluations/questions", response_model=list[EvaluationQuestionOut])
def list_evaluation_questions(member: Member, db: DbSession) -> list[EvaluationQuestion]:
    return list(
        db.scalars(
            select(EvaluationQuestion)
            .where(EvaluationQuestion.organization_id == member.organization.id)
            .order_by(EvaluationQuestion.created_at.desc())
        ).all()
    )


@router.post(
    "/knowledge/evaluations/questions", response_model=EvaluationQuestionOut, status_code=201
)
def create_evaluation_question(
    body: EvaluationQuestionCreate, admin: CsrfAdmin, db: DbSession
) -> EvaluationQuestion:
    question = EvaluationQuestion(
        organization_id=admin.organization.id,
        created_by=admin.user.id,
        question=body.question.strip(),
        scenario=body.scenario,
        expected_behavior=body.expected_behavior,
        expected_evidence=[item.strip() for item in body.expected_evidence if item.strip()],
        expected_answer=body.expected_answer,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.post("/knowledge/evaluations/questions/{question_id}/run", response_model=EvaluationRunOut)
def run_evaluation(
    question_id: uuid.UUID,
    admin: CsrfAdmin,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(organization_embedder)],
    chat: Annotated[ChatClient, Depends(organization_chat)],
) -> EvaluationRun:
    question = db.scalar(
        select(EvaluationQuestion).where(
            EvaluationQuestion.id == question_id,
            EvaluationQuestion.organization_id == admin.organization.id,
        )
    )
    if question is None:
        raise AppError(404, "evaluation_not_found", "Evaluation question not found")
    hits = search_chunks(db, admin.organization.id, question.question, embedder)
    source_rows = [
        {
            "document_id": str(hit.document_id),
            "document_title": hit.document_title,
            "chunk_id": str(hit.chunk_id),
            "score": hit.score,
        }
        for hit in hits
    ]
    haystack = "\n".join(hit.content.lower() for hit in hits)
    evidence_match = bool(question.expected_evidence) and all(
        term.lower() in haystack for term in question.expected_evidence
    )
    expected_fallback = question.expected_behavior in {"fallback", "handoff"}
    behavior_match = evidence_match if not expected_fallback else not evidence_match
    try:
        ai_result = evaluate_response(
            db,
            admin.organization.id,
            question.question,
            embedder,
            chat,
        )
    except AppError as exc:
        ai_result = {
            "response": "A team member should review this request.",
            "grounding": "provider_failure",
            "evidence_confidence": 0.0,
            "source_count": len(source_rows),
            "escalated": True,
            "reason": exc.code,
        }
    actual_behavior = {
        "grounded": "answer",
        "fallback": "fallback",
        "handoff": "handoff",
    }.get(str(ai_result["grounding"]), "provider_failure")
    behavior_match = behavior_match and actual_behavior == question.expected_behavior
    if question.expected_answer:
        behavior_match = (
            behavior_match
            and question.expected_answer.casefold() in str(ai_result["response"]).casefold()
        )
    case_result = {
        "scenario": question.scenario,
        "expected_behavior": question.expected_behavior,
        "evidence_relevance": evidence_match,
        "source_attribution": bool(source_rows) if question.expected_behavior == "answer" else True,
        "side_effects": "none",
        "actual_behavior": actual_behavior,
        "response_length": len(str(ai_result["response"])),
        "evidence_confidence": ai_result["evidence_confidence"],
        "fallback_reason": ai_result["reason"],
    }
    run = EvaluationRun(
        organization_id=admin.organization.id,
        question_id=question.id,
        model_identifier="deterministic-retrieval-evaluator",
        configuration_version="retrieval-v1",
        retrieved_sources=source_rows,
        evidence_match=evidence_match,
        answer_grounded=behavior_match,
        failure_reason=None
        if behavior_match
        else "evaluation behavior did not match expected outcome",
        case_result=case_result,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.post(
    "/knowledge/evaluations/questions/{question_id}/run-inbox/{conversation_id}",
    response_model=EvaluationRunOut,
)
def run_inbox_evaluation(
    question_id: uuid.UUID,
    conversation_id: uuid.UUID,
    admin: CsrfAdmin,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(organization_embedder)],
    chat: Annotated[ChatClient, Depends(organization_chat)],
) -> EvaluationRun:
    question = db.scalar(
        select(EvaluationQuestion).where(
            EvaluationQuestion.id == question_id,
            EvaluationQuestion.organization_id == admin.organization.id,
        )
    )
    if question is None:
        raise AppError(404, "evaluation_not_found", "Evaluation question not found")
    result = evaluate_inbox_draft(
        db,
        admin.organization.id,
        conversation_id,
        question.question,
        embedder,
        chat,
    )
    behavior = "handoff" if result["grounding"] != "grounded" else "answer"
    passed = behavior == question.expected_behavior
    run = EvaluationRun(
        organization_id=admin.organization.id,
        question_id=question.id,
        model_identifier="inbox-drafting-evaluator",
        configuration_version="inbox-draft-v1",
        retrieved_sources=[],
        evidence_match=result["grounding"] == "grounded",
        answer_grounded=passed,
        failure_reason=None if passed else "Inbox drafting behavior did not match expected outcome",
        case_result={
            "scenario": question.scenario,
            "actual_behavior": behavior,
            "side_effects": "none",
            "approval_created": False,
            "response_length": len(str(result["response"])),
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("/knowledge/evaluations/compare")
def compare_evaluation_runs(member: Member, db: DbSession) -> dict[str, object]:
    rows = list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.organization_id == member.organization.id)
            .order_by(EvaluationRun.created_at.desc())
            .limit(200)
        ).all()
    )
    if not rows:
        return {"current": None, "previous": None, "regressions": [], "improvements": []}
    current = rows[0]
    previous = next((row for row in rows[1:] if row.question_id == current.question_id), None)
    regressions: list[dict[str, object]] = []
    improvements: list[dict[str, object]] = []
    if previous is not None and current.answer_grounded != previous.answer_grounded:
        target = regressions if not current.answer_grounded else improvements
        target.append(
            {
                "question_id": str(current.question_id),
                "from": previous.answer_grounded,
                "to": current.answer_grounded,
            }
        )
    return {
        "current": EvaluationRunOut.model_validate(current).model_dump(mode="json"),
        "previous": None
        if previous is None
        else EvaluationRunOut.model_validate(previous).model_dump(mode="json"),
        "regressions": regressions,
        "improvements": improvements,
    }


@router.get("/knowledge/evaluations/runs", response_model=list[EvaluationRunOut])
def list_evaluation_runs(member: Member, db: DbSession) -> list[EvaluationRun]:
    return list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.organization_id == member.organization.id)
            .order_by(EvaluationRun.created_at.desc())
            .limit(100)
        ).all()
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


@router.get("/documents/{document_id}/preview", response_model=DocumentPreview)
def preview_document(
    document_id: uuid.UUID, member: Member, db: DbSession
) -> DocumentPreview:
    filename, excerpt, truncated = service.document_preview(db, member.organization.id, document_id)
    return DocumentPreview(filename=filename, excerpt=excerpt, truncated=truncated)


@router.post("/documents/{document_id}/archive", response_model=DocumentOut)
def archive_document(
    document_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> DocumentOut:
    return DocumentOut.model_validate(
        service.archive_document(db, member.organization.id, document_id)
    )


@router.post("/documents/{document_id}/restore", response_model=DocumentOut)
def restore_document(
    document_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> DocumentOut:
    return DocumentOut.model_validate(
        service.restore_document(db, member.organization.id, document_id)
    )


@router.post("/documents/{document_id}/content", response_model=DocumentOut)
def replace_document(
    document_id: uuid.UUID,
    member: CsrfMember,
    db: DbSession,
    file: UploadFile,
) -> DocumentOut:
    payload = file.file.read()
    current = service.get_document(db, member.organization.id, document_id)
    growth = max(0, len(payload) - current.byte_size)
    if growth:
        enforce_limit(db, member.organization.id, "knowledge_storage_bytes", growth)
    document = service.replace_document(
        db,
        member.organization.id,
        document_id,
        filename=file.filename or "document.txt",
        media_type=file.content_type or "application/octet-stream",
        payload=payload,
    )
    return DocumentOut.model_validate(document)


@router.post("/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(
    document_id: uuid.UUID,
    member: CsrfMember,
    db: DbSession,
) -> DocumentOut:
    document = service.mark_reindex(db, member.organization.id, document_id)
    return DocumentOut.model_validate(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_document(db, member.organization.id, document_id)
    return Response(status_code=204)
