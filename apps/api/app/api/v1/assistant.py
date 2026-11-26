import json
import time
import uuid
from collections.abc import Iterator
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.core.errors import AppError
from app.domains.assistant import operations, service
from app.domains.assistant.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationRename,
    MessageCreate,
    ProposalOut,
    ProposalSubmit,
    ReplyOut,
)
from app.domains.billing.service import meter_assistant_request
from app.domains.identity.dependencies import CsrfMember, DbSession, Member
from app.domains.observability.tracing import record_operation
from app.integrations.language import (
    ChatClient,
    EmbeddingClient,
    get_chat_client,
    get_embedding_client,
)

router = APIRouter(prefix="/organizations/{organization_id}", tags=["assistant"])


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


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    member: Member,
    db: DbSession,
    retention: Literal["active", "archived"] = "active",
    q: str | None = None,
) -> list[ConversationOut]:
    rows = service.list_conversations(
        db, member.organization.id, member.user.id, retention=retention, q=q
    )
    return [ConversationOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationCreate, member: CsrfMember, db: DbSession
) -> ConversationOut:
    conversation = service.create_conversation(
        db, member.organization.id, member.user.id, body.title
    )
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: uuid.UUID, body: ConversationRename, member: CsrfMember, db: DbSession
) -> ConversationOut:
    conversation = service.rename_conversation(
        db, member.organization.id, member.user.id, conversation_id, body.title
    )
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.post("/conversations/{conversation_id}/archive", response_model=ConversationOut)
def archive_conversation(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> ConversationOut:
    conversation = service.archive_conversation(
        db, member.organization.id, member.user.id, conversation_id
    )
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.post("/conversations/{conversation_id}/restore", response_model=ConversationOut)
def restore_conversation(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> ConversationOut:
    conversation = service.restore_conversation(
        db, member.organization.id, member.user.id, conversation_id
    )
    return ConversationOut.model_validate(conversation, from_attributes=True)


@router.post(
    "/conversations/{conversation_id}/proposals/{proposal_id}/submit",
    response_model=ProposalOut,
)
def submit_proposal(
    conversation_id: uuid.UUID,
    proposal_id: uuid.UUID,
    member: CsrfMember,
    db: DbSession,
    body: ProposalSubmit | None = None,
) -> ProposalOut:
    conversation = service.get_conversation(
        db, member.organization.id, member.user.id, conversation_id
    )
    submitted = body or ProposalSubmit()
    return operations.submit_proposal(
        db,
        conversation,
        proposal_id,
        member.user.id,
        submitted.starts_at,
        submitted.ends_at,
    )


@router.post(
    "/conversations/{conversation_id}/proposals/{proposal_id}/dismiss",
    response_model=ProposalOut,
)
def dismiss_proposal(
    conversation_id: uuid.UUID, proposal_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> ProposalOut:
    conversation = service.get_conversation(
        db, member.organization.id, member.user.id, conversation_id
    )
    return operations.dismiss_proposal(db, conversation, proposal_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID, member: Member, db: DbSession
) -> ConversationDetail:
    conversation = service.get_conversation(
        db, member.organization.id, member.user.id, conversation_id
    )
    detail = ConversationOut.model_validate(conversation, from_attributes=True)
    return ConversationDetail(
        **detail.model_dump(),
        messages=service.list_messages(db, conversation.id),
    )


@router.post("/conversations/{conversation_id}/messages", response_model=ReplyOut)
def create_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    member: CsrfMember,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(organization_embedder)],
    chat: Annotated[ChatClient, Depends(organization_chat)],
) -> ReplyOut:
    service.get_conversation(db, member.organization.id, member.user.id, conversation_id)
    meter_assistant_request(db, member.organization.id)
    turn = service.prepare_turn(
        db,
        member.organization.id,
        member.user.id,
        conversation_id,
        body.content,
        embedder,
        chat,
    )
    _require_model(db, turn, chat)
    started = time.perf_counter()
    try:
        result = service.complete_turn(db, turn, chat)
        record_operation(
            operation="assistant_response",
            status="escalated" if turn.escalation_reason else "succeeded",
            organization_id=member.organization.id,
            latency_ms=round((time.perf_counter() - started) * 1000),
            provider=getattr(chat, "provider", None),
            model_name=getattr(chat, "model", None),
            detail={
                "grounding": "grounded" if turn.documents or turn.crm_records else "none",
                "evidence_confidence": turn.evidence_confidence,
                "escalation_reason": turn.escalation_reason,
            },
        )
        return result
    except AppError as exc:
        service.record_provider_failure(db, turn.conversation, exc.message)
        record_operation(
            operation="assistant_response",
            status="failed",
            organization_id=member.organization.id,
            latency_ms=round((time.perf_counter() - started) * 1000),
            provider=getattr(chat, "provider", None),
            model_name=getattr(chat, "model", None),
            error_code=exc.code,
            detail={"grounding": "failed", "fallback_reason": exc.code},
        )
        raise


@router.post("/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    member: CsrfMember,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(organization_embedder)],
    chat: Annotated[ChatClient, Depends(organization_chat)],
) -> StreamingResponse:
    organization_id = member.organization.id
    service.get_conversation(db, organization_id, member.user.id, conversation_id)
    meter_assistant_request(db, organization_id)
    turn = service.prepare_turn(
        db,
        member.organization.id,
        member.user.id,
        conversation_id,
        body.content,
        embedder,
        chat,
    )
    _require_model(db, turn, chat)

    def events() -> Iterator[str]:
        parts: list[str] = []
        started = time.perf_counter()
        try:
            for phase in turn.phases:
                if phase in {"preparing", "searching_crm", "retrieving_documents"}:
                    yield _event("phase", {"phase": phase})
            if turn.holds_evidence():
                yield _event("phase", {"phase": "verifying"})
                for token in service.stream_turn(turn, chat):
                    parts.append(token)
                    # A comment keeps the response cancellable without showing the draft.
                    yield ": verifying\n\n"
            else:
                if turn.needs_model:
                    yield _event("phase", {"phase": "streaming"})
                for token in service.stream_turn(turn, chat):
                    parts.append(token)
                    yield _event("token", {"text": token})
            answer = turn.refusal if turn.refusal is not None else "".join(parts).strip()
            if turn.needs_model and not answer:
                raise AppError(502, "llm_failed", "The language model returned an empty answer")
            reply = service.save_completed_turn(db, turn, answer or service.NO_RECORDS)
            record_operation(
                operation="assistant_response",
                organization_id=organization_id,
                status="escalated" if turn.escalation_reason else "succeeded",
                latency_ms=round((time.perf_counter() - started) * 1000),
                provider=getattr(chat, "provider", None),
                model_name=getattr(chat, "model", None),
                detail={"grounding": "grounded" if reply.message.sources else "none"},
            )
            if turn.holds_evidence():
                yield _event("token", {"text": reply.message.content})
            yield _event("done", reply.model_dump(mode="json"))
        except AppError as exc:
            service.record_provider_failure(db, turn.conversation, exc.message)
            record_operation(
                operation="assistant_response",
                organization_id=organization_id,
                status="failed",
                latency_ms=round((time.perf_counter() - started) * 1000),
                error_code=exc.code,
            )
            yield _event("error", {"code": exc.code, "message": exc.message})

    return StreamingResponse(events(), media_type="text/event-stream")


def _require_model(
    db: DbSession,
    turn: service.PreparedTurn,
    chat: ChatClient,
) -> None:
    if not turn.needs_model:
        return
    try:
        chat.ensure_configured()
    except AppError as exc:
        service.record_provider_failure(db, turn.conversation, exc.message)
        raise


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"
