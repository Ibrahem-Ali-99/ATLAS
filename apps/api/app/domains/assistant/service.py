import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.assistant.models import (
    Conversation,
    Message,
    MessageRole,
    MessageSource,
    SourceKind,
)
from app.domains.assistant.schemas import MessageOut, ReplyOut, SourceOut
from app.domains.crm.service import search_records
from app.domains.knowledge.retrieval import RetrievedChunk, search_chunks
from app.integrations.language import ChatClient, EmbeddingClient

NO_RECORDS = "I could not find relevant company documents or CRM records for that question."
UNTITLED = "New conversation"
_EMBEDDING_UNAVAILABLE = {
    "embedding_unavailable",
    "embedding_unauthorized",
    "embedding_timeout",
    "embedding_rate_limited",
    "embedding_dimension_mismatch",
}
SYSTEM_PROMPT = (
    "You are the ATLAS assistant for one organization. "
    "Use only the document excerpts and CRM records in the user message. "
    "Document excerpts are company files. CRM records are live customer data. "
    "Say which kind of record you used. "
    "If a section is empty, say that kind of information was not found. "
    "Do not invent names, numbers, citations, or records."
)


@dataclass
class PreparedTurn:
    conversation: Conversation
    needs_model: bool
    system_prompt: str
    user_prompt: str
    documents: list[RetrievedChunk]
    crm_records: list[dict[str, str]]
    document_search: str
    refusal: str | None = None


def conversation_title(content: str) -> str:
    """Name a new conversation from its first question, without calling a model."""
    collapsed = " ".join(content.split())
    if not collapsed:
        return "Untitled conversation"
    limit = 72
    if len(collapsed) <= limit:
        return collapsed
    shortened = collapsed[:limit].rsplit(" ", 1)[0].rstrip(".,;:!?")
    if len(shortened) < 12:
        shortened = collapsed[:limit].rstrip()
    return shortened


def list_conversations(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.organization_id == organization_id, Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        ).all()
    )


def create_conversation(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, title: str | None
) -> Conversation:
    conversation = Conversation(
        organization_id=organization_id,
        user_id=user_id,
        title=(title or UNTITLED)[:200],
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise AppError(404, "not_found", "Resource not found")
    return conversation


def list_messages(db: Session, conversation_id: uuid.UUID) -> list[MessageOut]:
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    ).all()
    result: list[MessageOut] = []
    for message in messages:
        sources = db.scalars(
            select(MessageSource)
            .where(MessageSource.message_id == message.id)
            .order_by(MessageSource.title.asc())
        ).all()
        result.append(_message_out(message, list(sources)))
    return result


def prepare_turn(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    embedder: EmbeddingClient,
) -> PreparedTurn:
    conversation = get_conversation(db, organization_id, user_id, conversation_id)
    if conversation.title == UNTITLED:
        conversation.title = conversation_title(content)
    db.add(
        Message(
            conversation_id=conversation.id,
            organization_id=organization_id,
            role=MessageRole.user,
            content=content.strip(),
        )
    )
    db.commit()
    crm_records = search_records(db, organization_id, content)
    documents: list[RetrievedChunk] = []
    document_search = "empty"
    try:
        documents = search_chunks(db, organization_id, content, embedder)
        document_search = "ready" if documents else "empty"
    except AppError as exc:
        if exc.code == "embedding_unconfigured" and crm_records:
            document_search = "unconfigured"
        elif exc.code in _EMBEDDING_UNAVAILABLE and crm_records:
            document_search = "unavailable"
        else:
            record_provider_failure(db, conversation, exc.message)
            raise
    if not documents and not crm_records:
        saved = _save_answer(
            db,
            conversation,
            NO_RECORDS,
            [],
            [],
        )
        return PreparedTurn(
            conversation=conversation,
            needs_model=False,
            system_prompt=SYSTEM_PROMPT,
            user_prompt="",
            documents=[],
            crm_records=[],
            document_search=document_search,
            refusal=saved.content,
        )
    return PreparedTurn(
        conversation=conversation,
        needs_model=True,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_prompt(content, documents, crm_records),
        documents=documents,
        crm_records=crm_records,
        document_search=document_search,
    )


def record_provider_failure(db: Session, conversation: Conversation, message: str) -> None:
    _save_answer(db, conversation, message, [], [])


def complete_turn(db: Session, turn: PreparedTurn, client: ChatClient) -> ReplyOut:
    if turn.needs_model:
        answer = client.complete(turn.system_prompt, turn.user_prompt).strip()
        if not answer:
            raise AppError(502, "llm_failed", "The language model returned an empty answer")
    else:
        answer = turn.refusal or NO_RECORDS
    return save_completed_turn(db, turn, answer)


def save_completed_turn(db: Session, turn: PreparedTurn, answer: str) -> ReplyOut:
    if turn.refusal is not None:
        message = _latest_assistant(db, turn.conversation.id)
    else:
        saved = _save_answer(db, turn.conversation, answer, turn.documents, turn.crm_records)
        message = _message_out(saved, _sources_for(db, saved.id))
    search = turn.document_search
    if search not in {"ready", "empty", "unconfigured", "unavailable"}:
        search = "empty"
    return ReplyOut(conversation_id=turn.conversation.id, message=message, document_search=search)  # type: ignore[arg-type]


def stream_turn(turn: PreparedTurn, client: ChatClient) -> Iterator[str]:
    if turn.refusal is not None:
        yield turn.refusal
        return
    yield from client.stream(turn.system_prompt, turn.user_prompt)


def _prompt(
    question: str, documents: list[RetrievedChunk], crm_records: list[dict[str, str]]
) -> str:
    document_lines = ["DOCUMENT EXCERPTS:"]
    if documents:
        for excerpt in documents:
            page = f" page {excerpt.page_number}" if excerpt.page_number is not None else ""
            document_lines.append(f"- {excerpt.document_title}{page}: {excerpt.content[:700]}")
    else:
        document_lines.append("- none")
    crm_lines = ["CRM RECORDS:"]
    if crm_records:
        for record in crm_records:
            crm_lines.append(
                f"- {record['record_type']} {record['title']}: {record['excerpt'][:400]}"
            )
    else:
        crm_lines.append("- none")
    return "\n".join([*document_lines, *crm_lines, "", f"QUESTION: {question}"])


def _save_answer(
    db: Session,
    conversation: Conversation,
    answer: str,
    documents: list[RetrievedChunk],
    crm_records: list[dict[str, str]],
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        organization_id=conversation.organization_id,
        role=MessageRole.assistant,
        content=answer,
    )
    db.add(message)
    db.flush()
    for excerpt in documents:
        db.add(
            MessageSource(
                message_id=message.id,
                organization_id=conversation.organization_id,
                kind=SourceKind.document,
                document_id=excerpt.document_id,
                chunk_id=excerpt.chunk_id,
                page_number=excerpt.page_number,
                title=excerpt.document_title[:200],
                excerpt=excerpt.content[:500],
            )
        )
    for record in crm_records:
        db.add(
            MessageSource(
                message_id=message.id,
                organization_id=conversation.organization_id,
                kind=SourceKind.crm,
                record_type=record["record_type"],
                record_id=uuid.UUID(record["record_id"]),
                title=record["title"][:200],
                excerpt=record["excerpt"][:500],
            )
        )
    db.commit()
    db.refresh(message)
    return message


def _latest_assistant(db: Session, conversation_id: uuid.UUID) -> MessageOut:
    message = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == MessageRole.assistant)
        .order_by(Message.created_at.desc())
    )
    if message is None:
        raise AppError(500, "internal_error", "An unexpected error occurred")
    return _message_out(message, _sources_for(db, message.id))


def _sources_for(db: Session, message_id: uuid.UUID) -> list[MessageSource]:
    return list(
        db.scalars(select(MessageSource).where(MessageSource.message_id == message_id)).all()
    )


def _message_out(message: Message, sources: list[MessageSource]) -> MessageOut:
    role = message.role.value if isinstance(message.role, MessageRole) else str(message.role)
    return MessageOut(
        id=message.id,
        role=role,  # type: ignore[arg-type]
        content=message.content,
        created_at=message.created_at,
        sources=[_source_out(source) for source in sources],
    )


def _source_out(source: MessageSource) -> SourceOut:
    kind = source.kind.value if isinstance(source.kind, SourceKind) else str(source.kind)
    return SourceOut(
        kind=kind,  # type: ignore[arg-type]
        title=source.title,
        excerpt=source.excerpt,
        document_id=source.document_id,
        chunk_id=source.chunk_id,
        page_number=source.page_number,
        record_type=source.record_type,
        record_id=source.record_id,
    )
