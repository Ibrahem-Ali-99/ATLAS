import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.assistant import operations, service
from app.domains.assistant.inference_guard import (
    DETERMINISTIC_FALLBACK,
    assess_public_inference,
    finish_public_inference,
)
from app.domains.assistant.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationRename,
    ExecutionOut,
    ExecutionPage,
    ExecutionStepOut,
    MessageCreate,
    ProposalOut,
    ProposalSubmit,
    ReplyOut,
)
from app.domains.billing.service import meter_assistant_request
from app.domains.demo.access import is_visitor_slug
from app.domains.demo.service import enforce_demo_assistant
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


@dataclass
class _VisitorSlot:
    chat: ChatClient | None = None
    held: bool = False
    denied: str | None = None


def _visitor_slot(db: DbSession, member: Member, text: str) -> _VisitorSlot:
    """Apply the public budget to a visitor Assistant turn when the switch is on."""

    if not is_visitor_slug(member.organization.slug):
        return _VisitorSlot()
    if not get_settings().public_inference_enabled:
        return _VisitorSlot()
    decision = assess_public_inference(
        f"assistant:{member.organization.id}:{member.user.id}",
        text,
        hold_slot=True,
    )
    if not decision.allowed:
        return _VisitorSlot(denied=decision.message)
    return _VisitorSlot(
        chat=get_chat_client(
            db,
            member.organization.id,
            public_inference=True,
            max_output_tokens=get_settings().public_inference_max_output_tokens,
        ),
        held=True,
    )


def organization_chat(request: Request, member: Member, db: DbSession) -> ChatClient:
    override = request.app.dependency_overrides.get(get_chat_client)
    if override is not None:
        return cast(ChatClient, override())
    return get_chat_client(db, member.organization.id)


@router.get("/assistant-executions", response_model=ExecutionPage)
def list_assistant_executions(member: Member, db: DbSession, page: int = 1) -> ExecutionPage:
    from app.domains.assistant import executions

    current = page if page >= 1 else 1
    rows, total = executions.list_executions(
        db,
        member.organization.id,
        member.user.id,
        member.membership.role,
        page=current,
        page_size=20,
    )
    return ExecutionPage(
        items=[_execution_detail(row, executions.steps_for_execution(db, row.id)) for row in rows],
        page=current,
        page_size=20,
        total=total,
    )


@router.get("/assistant-executions/{execution_id}", response_model=ExecutionOut)
def get_assistant_execution(
    execution_id: uuid.UUID, member: Member, db: DbSession
) -> ExecutionOut:
    from app.domains.assistant import executions

    row, steps = executions.get_execution(
        db,
        member.organization.id,
        member.user.id,
        member.membership.role,
        execution_id,
    )
    return _execution_detail(row, steps)


def _execution_detail(row: object, steps: list[object]) -> ExecutionOut:
    from app.domains.assistant.models import AssistantExecution, AssistantExecutionStep

    if not isinstance(row, AssistantExecution):
        raise AppError(500, "internal_error", "An unexpected error occurred")
    parsed = [step for step in steps if isinstance(step, AssistantExecutionStep)]
    status = row.status if row.status in {"running", "completed", "failed"} else "failed"
    return ExecutionOut(
        id=row.id,
        conversation_id=row.conversation_id,
        request=row.request,
        status=status,  # type: ignore[arg-type]
        tools=list(row.selected_tools),
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        error_message=row.error_message,
        started_at=row.started_at,
        finished_at=row.finished_at,
        steps=[
            ExecutionStepOut(
                sequence=step.sequence,
                tool_name=step.tool_name,
                status=step.status,  # type: ignore[arg-type]
                duration_ms=step.duration_ms,
                arguments=step.arguments,
                records=step.records,
                error_message=step.error_message,
                recovery=step.recovery,
            )
            for step in parsed
        ],
    )


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
    enforce_demo_assistant(db, member.organization)
    meter_assistant_request(db, member.organization.id)
    slot = _visitor_slot(db, member, body.content)
    if slot.denied is not None:
        return service.reject_public_turn(
            db,
            member.organization.id,
            member.user.id,
            conversation_id,
            body.content,
            slot.denied,
        )
    if slot.chat is not None:
        chat = slot.chat
    turn: service.PreparedTurn | None = None
    started = time.perf_counter()
    try:
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
        failure = DETERMINISTIC_FALLBACK if slot.held else exc.message
        if turn is not None:
            service.record_provider_failure(db, turn.conversation, failure)
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
        if slot.held:
            raise AppError(exc.status_code, exc.code, failure) from exc
        raise
    finally:
        if slot.held:
            finish_public_inference()


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
    enforce_demo_assistant(db, member.organization)
    meter_assistant_request(db, organization_id)
    slot = _visitor_slot(db, member, body.content)
    if slot.denied is not None:
        reply = service.reject_public_turn(
            db,
            organization_id,
            member.user.id,
            conversation_id,
            body.content,
            slot.denied,
        )

        def denied_events() -> Iterator[str]:
            yield _event("done", reply.model_dump(mode="json"))

        return StreamingResponse(denied_events(), media_type="text/event-stream")
    if slot.chat is not None:
        chat = slot.chat
    turn: service.PreparedTurn | None = None
    try:
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
    except AppError as exc:
        failure = DETERMINISTIC_FALLBACK if slot.held else exc.message
        if turn is not None:
            service.record_provider_failure(db, turn.conversation, failure)
        if slot.held:
            finish_public_inference()
        raise
    except Exception:
        if slot.held:
            finish_public_inference()
        raise

    assert turn is not None

    def events() -> Iterator[str]:
        parts: list[str] = []
        started = time.perf_counter()
        try:
            for phase in turn.phases:
                if phase in {
                    "preparing",
                    "selecting_tools",
                    "searching_crm",
                    "retrieving_documents",
                }:
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
            service.note_model_usage(db, turn, chat)
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
            failure = DETERMINISTIC_FALLBACK if slot.held else exc.message
            service.record_provider_failure(db, turn.conversation, failure)
            record_operation(
                operation="assistant_response",
                organization_id=organization_id,
                status="failed",
                latency_ms=round((time.perf_counter() - started) * 1000),
                error_code=exc.code,
            )
            yield _event("error", {"code": exc.code, "message": failure})
        finally:
            if slot.held:
                finish_public_inference()

    return StreamingResponse(events(), media_type="text/event-stream")


def _require_model(
    db: DbSession,
    turn: service.PreparedTurn,
    chat: ChatClient,
) -> None:
    if not turn.needs_model:
        return
    chat.ensure_configured()


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"
