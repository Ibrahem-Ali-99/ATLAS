import json
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.core.errors import AppError
from app.domains.assistant import service
from app.domains.assistant.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageCreate,
    ReplyOut,
)
from app.domains.identity.dependencies import CsrfMember, DbSession, Member
from app.integrations.language import (
    ChatClient,
    EmbeddingClient,
    get_chat_client,
    get_embedding_client,
)

router = APIRouter(prefix="/organizations/{organization_id}", tags=["assistant"])


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(member: Member, db: DbSession) -> list[ConversationOut]:
    rows = service.list_conversations(db, member.organization.id, member.user.id)
    return [ConversationOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationCreate, member: CsrfMember, db: DbSession
) -> ConversationOut:
    conversation = service.create_conversation(
        db, member.organization.id, member.user.id, body.title
    )
    return ConversationOut.model_validate(conversation, from_attributes=True)


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
    embedder: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    chat: Annotated[ChatClient, Depends(get_chat_client)],
) -> ReplyOut:
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
    try:
        return service.complete_turn(db, turn, chat)
    except AppError as exc:
        service.record_provider_failure(db, turn.conversation, exc.message)
        raise


@router.post("/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    member: CsrfMember,
    db: DbSession,
    embedder: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    chat: Annotated[ChatClient, Depends(get_chat_client)],
) -> StreamingResponse:
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
            if turn.holds_evidence():
                yield _event("token", {"text": reply.message.content})
            yield _event("done", reply.model_dump(mode="json"))
        except AppError as exc:
            service.record_provider_failure(db, turn.conversation, exc.message)
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
