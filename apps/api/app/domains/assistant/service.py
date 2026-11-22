import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.assistant.catalog import InventoryDocument, ReadAnswer
from app.domains.assistant.catalog import answer_companies as read_companies
from app.domains.assistant.catalog import answer_documents as read_documents
from app.domains.assistant.catalog import answer_inquiries as read_inquiries
from app.domains.assistant.catalog import answer_inventory as read_inventory
from app.domains.assistant.catalog import answer_leads as read_leads
from app.domains.assistant.models import (
    Conversation,
    Message,
    MessageRole,
    MessageSource,
    SourceKind,
)
from app.domains.assistant.prompts import (
    GENERAL_SYSTEM,
    GROUNDED_SYSTEM,
    general_prompt,
    grounded_prompt,
)
from app.domains.assistant.routing import (
    CAPABILITY_ANSWER,
    CLASSIFIER_SYSTEM,
    GREETING_ANSWER,
    MUTATION_ANSWER,
    Intent,
    allows_ungrounded_chat,
    parse_classifier_intent,
    recall_answer,
    refers_to_earlier_record,
    route_question,
    unsupported_without_evidence,
)
from app.domains.assistant.schemas import MessageOut, ReplyOut, SourceOut
from app.domains.crm.service import search_records
from app.domains.knowledge.models import Chunk
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
    phases: list[str] = field(default_factory=list)
    inventory_documents: list[InventoryDocument] = field(default_factory=list)


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
    chat: ChatClient | None = None,
) -> PreparedTurn:
    conversation = get_conversation(db, organization_id, user_id, conversation_id)
    if conversation.title == UNTITLED:
        conversation.title = conversation_title(content)
    user_message = Message(
        conversation_id=conversation.id,
        organization_id=organization_id,
        role=MessageRole.user,
        content=content.strip(),
    )
    db.add(user_message)
    db.commit()
    history = _prior_turns(db, organization_id, conversation.id, user_message.id)
    titles = _recent_source_titles(db, organization_id, conversation.id, user_message.id, content)
    intent = route_question(content, has_history=bool(history))
    expand = refers_to_earlier_record(content)
    if intent is Intent.ambiguous:
        if titles:
            intent = Intent.grounded
            expand = True
        else:
            intent = _classify_ambiguous(chat, content)
    if intent is Intent.mutation:
        return _stored_reply(db, conversation, MUTATION_ANSWER, _phases())
    if intent is Intent.capability:
        return _stored_reply(db, conversation, CAPABILITY_ANSWER, _phases())
    if intent is Intent.greeting:
        return _stored_reply(db, conversation, GREETING_ANSWER, _phases())
    if intent is Intent.recall:
        opening = _opening_user_text(db, organization_id, conversation.id, user_message.id)
        return _stored_reply(db, conversation, recall_answer(history, opening), _phases())
    read = _catalog_answer(db, organization_id, intent)
    if read is not None:
        return _stored_read(db, conversation, read)
    if intent is Intent.general:
        return _general_turn(conversation, content, history, "skipped")
    return _grounded_turn(
        db, organization_id, conversation, content, embedder, history, titles, expand=expand
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
    if search not in {"ready", "empty", "unconfigured", "unavailable", "skipped"}:
        search = "empty"
    return ReplyOut(conversation_id=turn.conversation.id, message=message, document_search=search)  # type: ignore[arg-type]


def stream_turn(turn: PreparedTurn, client: ChatClient) -> Iterator[str]:
    if turn.refusal is not None:
        yield turn.refusal
        return
    yield from client.stream(turn.system_prompt, turn.user_prompt)


def _catalog_answer(db: Session, organization_id: uuid.UUID, intent: Intent) -> ReadAnswer | None:
    if intent is Intent.inventory:
        return read_inventory(db, organization_id)
    if intent is Intent.companies:
        return read_companies(db, organization_id)
    if intent is Intent.documents:
        return read_documents(db, organization_id)
    if intent is Intent.inquiries:
        return read_inquiries(db, organization_id)
    if intent is Intent.leads:
        return read_leads(db, organization_id)
    return None


def _classify_ambiguous(chat: ChatClient | None, content: str) -> Intent:
    if chat is None:
        return Intent.recall
    try:
        chat.ensure_configured()
        raw = chat.complete(CLASSIFIER_SYSTEM, content[:500])
    except AppError:
        return Intent.recall
    return parse_classifier_intent(raw) or Intent.recall


def _grounded_turn(
    db: Session,
    organization_id: uuid.UUID,
    conversation: Conversation,
    content: str,
    embedder: EmbeddingClient,
    history: list[tuple[str, str]],
    titles: list[str],
    *,
    expand: bool,
) -> PreparedTurn:
    query = _retrieval_query(content, history, titles, expand=expand)
    phases = _phases("searching_crm", "retrieving_documents")
    crm_records = search_records(db, organization_id, query)
    documents: list[RetrievedChunk] = []
    document_search = "empty"
    try:
        documents = search_chunks(db, organization_id, content, embedder)
        if not documents and _referenced_kind(content) == SourceKind.document.value:
            documents = _prior_document_chunks(db, organization_id, conversation.id)
        if not documents and expand and titles:
            documents = search_chunks(db, organization_id, "\n".join(titles), embedder)
        document_search = "ready" if documents else "empty"
    except AppError as exc:
        if exc.code == "embedding_unconfigured" and crm_records:
            document_search = "unconfigured"
        elif exc.code in _EMBEDDING_UNAVAILABLE and crm_records:
            document_search = "unavailable"
        else:
            record_provider_failure(db, conversation, exc.message)
            raise
    if documents or crm_records:
        return PreparedTurn(
            conversation=conversation,
            needs_model=True,
            system_prompt=GROUNDED_SYSTEM,
            user_prompt=grounded_prompt(content, documents, crm_records, history),
            documents=documents,
            crm_records=crm_records,
            document_search=document_search,
            phases=phases,
        )
    if allows_ungrounded_chat(content) and not unsupported_without_evidence(content):
        return _general_turn(conversation, content, history, "skipped", phases)
    saved = _save_answer(db, conversation, NO_RECORDS, [], [])
    return PreparedTurn(
        conversation=conversation,
        needs_model=False,
        system_prompt=GROUNDED_SYSTEM,
        user_prompt="",
        documents=[],
        crm_records=[],
        document_search=document_search,
        refusal=saved.content,
        phases=phases,
    )


def _general_turn(
    conversation: Conversation,
    content: str,
    history: list[tuple[str, str]],
    document_search: str,
    phases: list[str] | None = None,
) -> PreparedTurn:
    return PreparedTurn(
        conversation=conversation,
        needs_model=True,
        system_prompt=GENERAL_SYSTEM,
        user_prompt=general_prompt(content, history),
        documents=[],
        crm_records=[],
        document_search=document_search,
        phases=phases or _phases(),
    )


def _stored_read(db: Session, conversation: Conversation, read: ReadAnswer) -> PreparedTurn:
    phases = _phases()
    if read.searched_crm:
        phases.append("searching_crm")
    if read.searched_documents:
        phases.append("retrieving_documents")
    saved = _save_answer(db, conversation, read.content, [], read.crm_records, read.documents)
    return PreparedTurn(
        conversation=conversation,
        needs_model=False,
        system_prompt="",
        user_prompt="",
        documents=[],
        crm_records=read.crm_records,
        document_search="skipped",
        refusal=saved.content,
        phases=phases,
        inventory_documents=read.documents,
    )


def _stored_reply(
    db: Session, conversation: Conversation, content: str, phases: list[str]
) -> PreparedTurn:
    saved = _save_answer(db, conversation, content, [], [])
    return PreparedTurn(
        conversation=conversation,
        needs_model=False,
        system_prompt="",
        user_prompt="",
        documents=[],
        crm_records=[],
        document_search="skipped",
        refusal=saved.content,
        phases=phases,
    )


def _phases(*extra: str) -> list[str]:
    phases = ["preparing"]
    for name in extra:
        if name not in phases:
            phases.append(name)
    return phases


def _opening_user_text(
    db: Session,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_message_id: uuid.UUID,
) -> str | None:
    message = db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == organization_id,
            Message.id != current_message_id,
            Message.role == MessageRole.user,
        )
        .order_by(Message.created_at.asc())
        .limit(1)
    )
    if message is None:
        return None
    return message.content


def _prior_turns(
    db: Session,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_message_id: uuid.UUID,
) -> list[tuple[str, str]]:
    rows = list(
        db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.organization_id == organization_id,
                Message.id != current_message_id,
            )
            .order_by(Message.created_at.desc())
            .limit(8)
        ).all()
    )
    rows.reverse()
    return [(_role(message), message.content) for message in rows]


def _recent_source_titles(
    db: Session,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_message_id: uuid.UUID,
    question: str,
) -> list[str]:
    sources = db.scalars(
        select(MessageSource)
        .join(Message, Message.id == MessageSource.message_id)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == organization_id,
            Message.id != current_message_id,
            MessageSource.organization_id == organization_id,
        )
        .order_by(Message.created_at.desc())
    ).all()
    wanted = _referenced_kind(question)
    titles: list[str] = []
    for source in sources:
        kind = source.kind.value if isinstance(source.kind, SourceKind) else str(source.kind)
        if wanted is not None and kind != wanted:
            continue
        title = " ".join(source.title.split())
        if title and title not in titles:
            titles.append(title)
        if len(titles) == 4:
            break
    return titles


def _prior_document_chunks(
    db: Session, organization_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[RetrievedChunk]:
    """Re-read a chunk this conversation already cited. The model text is not the source."""
    sources = db.scalars(
        select(MessageSource)
        .join(Message, Message.id == MessageSource.message_id)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == organization_id,
            MessageSource.organization_id == organization_id,
            MessageSource.kind == SourceKind.document,
            MessageSource.chunk_id.is_not(None),
        )
        .order_by(Message.created_at.desc())
        .limit(3)
    ).all()
    found: list[RetrievedChunk] = []
    seen: set[uuid.UUID] = set()
    for source in sources:
        if source.chunk_id is None or source.chunk_id in seen:
            continue
        chunk = db.scalar(
            select(Chunk).where(
                Chunk.id == source.chunk_id, Chunk.organization_id == organization_id
            )
        )
        if chunk is None:
            continue
        seen.add(chunk.id)
        found.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=source.title,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                content=chunk.content,
                score=1.0,
            )
        )
    return found


def _referenced_kind(question: str) -> str | None:
    text = " ".join(question.lower().split())
    if re.search(r"\b(document|file|brochure)\b", text):
        return SourceKind.document.value
    if re.search(r"\b(company|companies|lead|leads|inquiry|inquiries|contact|contacts)\b", text):
        return SourceKind.crm.value
    return None


def _retrieval_query(
    question: str, history: list[tuple[str, str]], titles: list[str], *, expand: bool
) -> str:
    text = question.strip()
    if not expand:
        return text
    extra = list(titles[:4])
    for role, prior in reversed(history):
        if role == "user":
            clipped = " ".join(prior.split())[:300]
            if clipped and clipped not in extra:
                extra.append(clipped)
            break
    if not extra:
        return text
    return text + "\n" + "\n".join(extra)


def _role(message: Message) -> str:
    if isinstance(message.role, MessageRole):
        return message.role.value
    return str(message.role)


def _save_answer(
    db: Session,
    conversation: Conversation,
    answer: str,
    documents: list[RetrievedChunk],
    crm_records: list[dict[str, str]],
    inventory_documents: list[InventoryDocument] | None = None,
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
    for document in inventory_documents or []:
        db.add(
            MessageSource(
                message_id=message.id,
                organization_id=conversation.organization_id,
                kind=SourceKind.document,
                document_id=document.document_id,
                title=document.title[:200],
                excerpt=document.excerpt[:500],
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
