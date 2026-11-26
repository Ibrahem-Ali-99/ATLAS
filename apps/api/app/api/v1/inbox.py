# ruff: noqa: E501
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import AwareDatetime, BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType
from app.domains.approvals.service import create_approval
from app.domains.assistant.service import _configured_system
from app.domains.audit.service import record_event
from app.domains.automation.workflows import stage_lead_created
from app.domains.crm import service as crm
from app.domains.crm.models import Company, Contact, Inquiry, Lead, LeadStatus
from app.domains.crm.schemas import ContactCreate
from app.domains.identity.dependencies import CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.identity.models import Membership, Organization, User
from app.domains.identity.service import list_team
from app.domains.inbox.models import (
    InboxConversation,
    InboxMessage,
    InboxStatus,
    WidgetConfig,
    WidgetSession,
)
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.knowledge.retrieval import search_chunks
from app.integrations.language import get_chat_client, get_embedding_client
from app.integrations.whatsapp import normalize_phone

router = APIRouter(prefix="/organizations/{organization_id}/inbox", tags=["inbox"])
public_widget_router = APIRouter(prefix="/widget", tags=["website-chat"])


class MessageBody(BaseModel):
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    recipient: str = Field(min_length=3, max_length=320)
    template_name: str | None = Field(default=None, max_length=200)
    template_language: str = Field(default="en_US", max_length=20)


class InboundBody(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    sender: EmailStr
    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    channel: Literal["email"] = "email"


class AiReplyBody(BaseModel):
    instruction: str = Field(default="Draft a helpful reply", max_length=500)


def evaluate_inbox_draft(
    db: Session,
    organization_id: uuid.UUID,
    conversation_id: uuid.UUID,
    instruction: str,
    embedder: object,
    chat: object,
) -> dict[str, object]:
    """Evaluate Inbox drafting inputs without persisting a draft or approval."""
    row = _conversation(db, organization_id, conversation_id)
    messages = db.scalars(
        select(InboxMessage)
        .where(
            InboxMessage.conversation_id == row.id,
            InboxMessage.organization_id == organization_id,
        )
        .order_by(InboxMessage.created_at)
    ).all()
    context = "\n".join(f"{message.direction}: {message.body}" for message in messages[-12:])
    crm_context: list[str] = []
    if row.contact_id:
        contact = db.scalar(
            select(Contact).where(
                Contact.id == row.contact_id, Contact.organization_id == organization_id
            )
        )
        if contact:
            crm_context.append(f"Contact: {contact.full_name}; title: {contact.title or 'none'}")
    if row.lead_id:
        lead = db.scalar(
            select(Lead).where(Lead.id == row.lead_id, Lead.organization_id == organization_id)
        )
        if lead:
            crm_context.append(f"Lead: {lead.title}; stage: {lead.status.value}")
    hits = search_chunks(
        db,
        organization_id,
        f"{row.subject} {instruction}",
        embedder,  # type: ignore[arg-type]
        limit=3,
    )
    knowledge = "\n".join(f"{hit.document_title}: {hit.content}" for hit in hits)
    result = chat.complete(  # type: ignore[attr-defined]
        _configured_system(
            db,
            organization_id,
            "Draft a concise, factual customer reply. Return JSON with subject and body. "
            "Never invent facts, prices, policies, commitments, or delivery promises.",
        ),
        f"Subject: {row.subject}\nCRM: {'; '.join(crm_context)}\n"
        f"Knowledge:\n{knowledge}\nConversation:\n{context}\nInstruction: {instruction}",
    ).strip()
    return {
        "response": result[:12000],
        "source_count": len(hits),
        "grounding": "grounded" if hits else "insufficient_evidence",
        "side_effects": "none",
        "approval_created": False,
    }


def _human_request_reason(text: str) -> str | None:
    normalized = " ".join(text.lower().split())
    if re.search(r"\b(human|person|agent|representative|staff|support team)\b", normalized):
        return "Customer requested human support"
    return None


def _register_inbound(conversation: InboxConversation, body: str) -> None:
    conversation.unread_count += 1
    conversation.archived_at = None
    conversation.archived_by = None
    conversation.updated_at = datetime.now(UTC)
    reason = _human_request_reason(body)
    if reason:
        conversation.handoff_requested = True
        conversation.handoff_reason = reason
        conversation.ai_resumed = False
        conversation.status = InboxStatus.pending


def _conversation(
    db: DbSession, org: uuid.UUID, conversation_id: uuid.UUID, *, lock: bool = False
) -> InboxConversation:
    query = select(InboxConversation).where(
        InboxConversation.id == conversation_id, InboxConversation.organization_id == org
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise AppError(404, "conversation_not_found", "Conversation not found")
    return row


def _message_preview(body: str | None) -> str | None:
    if body is None:
        return None
    compact = " ".join(body.split())
    if not compact:
        return None
    if len(compact) <= 140:
        return compact
    return f"{compact[:139].rstrip()}..."


def _assignee_name(db: Session, row: InboxConversation) -> str | None:
    if row.assigned_to is None:
        return None
    return db.scalar(select(User.full_name).where(User.id == row.assigned_to))


def _customer_profile(
    db: Session, row: InboxConversation, contact: Contact | None
) -> dict[str, object]:
    company_name = None
    company_id = contact.company_id if contact else None
    if company_id is not None:
        company_name = db.scalar(
            select(Company.name).where(
                Company.id == company_id, Company.organization_id == row.organization_id
            )
        )
    inquiry = (
        db.scalar(
            select(Inquiry)
            .where(
                Inquiry.organization_id == row.organization_id,
                Inquiry.lead_id == row.lead_id,
                Inquiry.archived_at.is_(None),
            )
            .order_by(Inquiry.created_at.desc(), Inquiry.id)
            .limit(1)
        )
        if row.lead_id
        else None
    )
    return {
        "name": contact.full_name if contact else None,
        "email": contact.email if contact else None,
        "phone": contact.phone if contact else None,
        "company_id": company_id,
        "company_name": company_name,
        "inquiry_id": inquiry.id if inquiry else None,
        "inquiry_subject": inquiry.subject if inquiry else None,
    }


def _whatsapp_service_window(db: Session, row: InboxConversation) -> dict[str, object] | None:
    if row.channel != "whatsapp":
        return None
    latest = db.scalar(
        select(InboxMessage.created_at)
        .where(
            InboxMessage.organization_id == row.organization_id,
            InboxMessage.conversation_id == row.id,
            InboxMessage.channel == "whatsapp",
            InboxMessage.direction == "inbound",
        )
        .order_by(InboxMessage.created_at.desc(), InboxMessage.id)
        .limit(1)
    )
    closes_at = None if latest is None else latest + timedelta(hours=24)
    mode = _whatsapp_reply_mode(db, row)
    return {
        "open": closes_at is not None and datetime.now(UTC) < closes_at,
        "closes_at": closes_at,
        "provider": mode if mode in {"live", "test"} else "unavailable",
    }


def _queue_customer_name(
    contact_name: str | None, sender: str | None, direction: str | None
) -> str | None:
    if contact_name:
        return contact_name
    if direction == "inbound" and sender and sender.casefold() not in {"visitor", "atlas"}:
        return sender
    return None


@router.get("")
def list_inbox(
    member: Member,
    db: DbSession,
    q: str | None = None,
    assigned: Literal["all", "assigned", "unassigned", "mine"] = "all",
    channel: Literal["all", "email", "whatsapp", "webchat"] = "all",
    status: InboxStatus | None = None,
    retention: Literal["active", "archived"] = "active",
) -> list[dict[str, object]]:
    organization_id = member.organization.id
    ranked_messages = (
        select(
            InboxMessage.conversation_id.label("conversation_id"),
            InboxMessage.body.label("body"),
            InboxMessage.sender.label("sender"),
            InboxMessage.direction.label("direction"),
            func.row_number()
            .over(
                partition_by=InboxMessage.conversation_id,
                order_by=(InboxMessage.created_at.desc(), InboxMessage.id.desc()),
            )
            .label("rank"),
        )
        .where(
            InboxMessage.organization_id == organization_id,
            InboxMessage.delivery_status != "draft",
        )
        .subquery()
    )
    latest_message = select(ranked_messages).where(ranked_messages.c.rank == 1).subquery()
    query = (
        select(
            InboxConversation,
            Contact.full_name,
            Company.name,
            User.full_name,
            latest_message.c.body,
            latest_message.c.sender,
            latest_message.c.direction,
        )
        .outerjoin(Contact, Contact.id == InboxConversation.contact_id)
        .outerjoin(Company, Company.id == Contact.company_id)
        .outerjoin(User, User.id == InboxConversation.assigned_to)
        .outerjoin(latest_message, latest_message.c.conversation_id == InboxConversation.id)
        .where(InboxConversation.organization_id == organization_id)
        .order_by(InboxConversation.updated_at.desc(), InboxConversation.id.desc())
    )
    if retention == "archived":
        query = query.where(InboxConversation.archived_at.is_not(None))
    else:
        query = query.where(InboxConversation.archived_at.is_(None))
    if assigned == "assigned":
        query = query.where(InboxConversation.assigned_to.is_not(None))
    elif assigned == "unassigned":
        query = query.where(InboxConversation.assigned_to.is_(None))
    elif assigned == "mine":
        query = query.where(InboxConversation.assigned_to == member.user.id)
    if channel != "all":
        query = query.where(InboxConversation.channel == channel)
    if status is not None:
        query = query.where(InboxConversation.status == status)
    if q and q.strip():
        term = q.strip()
        message_match = (
            select(InboxMessage.id)
            .where(
                InboxMessage.conversation_id == InboxConversation.id,
                InboxMessage.organization_id == organization_id,
                InboxMessage.body.icontains(term, autoescape=True),
            )
            .exists()
        )
        query = query.where(
            or_(
                InboxConversation.subject.icontains(term, autoescape=True),
                Contact.full_name.icontains(term, autoescape=True),
                message_match,
            )
        )
    return [
        {
            "id": row.id,
            "subject": row.subject,
            "channel": row.channel,
            "status": row.status.value,
            "unread_count": row.unread_count,
            "contact_id": row.contact_id,
            "lead_id": row.lead_id,
            "assigned_to": row.assigned_to,
            "assignee_name": assignee_name,
            "archived_at": row.archived_at,
            "handoff_requested": row.handoff_requested,
            "handoff_reason": row.handoff_reason,
            "updated_at": row.updated_at,
            "customer_name": _queue_customer_name(contact_name, sender, direction),
            "company_name": company_name,
            "preview": _message_preview(preview),
        }
        for (
            row,
            contact_name,
            company_name,
            assignee_name,
            preview,
            sender,
            direction,
        ) in db.execute(query)
    ]


@router.get("/{conversation_id:uuid}")
def get_inbox(conversation_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    messages = db.scalars(
        select(InboxMessage)
        .where(
            InboxMessage.conversation_id == row.id,
            InboxMessage.organization_id == row.organization_id,
        )
        .order_by(InboxMessage.created_at, InboxMessage.id)
    ).all()
    contact = (
        db.scalar(
            select(Contact).where(
                Contact.id == row.contact_id, Contact.organization_id == row.organization_id
            )
        )
        if row.contact_id
        else None
    )
    return {
        "id": row.id,
        "subject": row.subject,
        "channel": row.channel,
        "status": row.status.value,
        "unread_count": row.unread_count,
        "updated_at": row.updated_at,
        "contact_id": row.contact_id,
        "lead_id": row.lead_id,
        "assigned_to": row.assigned_to,
        "handoff_requested": row.handoff_requested,
        "handoff_reason": row.handoff_reason,
        "handoff_accepted_at": row.handoff_accepted_at,
        "handoff_resolved_at": row.handoff_resolved_at,
        "ai_resumed": row.ai_resumed,
        "archived_at": row.archived_at,
        "assignee_name": _assignee_name(db, row),
        "customer": _customer_profile(db, row, contact),
        "whatsapp_service_window": _whatsapp_service_window(db, row),
        "reply_unavailable": _whatsapp_reply_unavailable(db, row),
        "whatsapp_reply_mode": _whatsapp_reply_mode(db, row),
        "reply_recipient": (
            contact.email
            if row.channel == "email"
            else contact.phone
            if row.channel == "whatsapp"
            else None
        )
        if contact
        else None,
        "messages": [
            {
                "id": msg.id,
                "sender": msg.sender,
                "recipient": msg.recipient,
                "body": msg.body,
                "direction": msg.direction,
                "delivery_status": msg.delivery_status,
                "channel": msg.channel,
                "created_at": msg.created_at,
            }
            for msg in messages
        ],
    }


class SeenConversation(BaseModel):
    updated_at: AwareDatetime


@router.patch("/{conversation_id}/read")
def mark_inbox_read(
    conversation_id: uuid.UUID, body: SeenConversation, member: CsrfMember, db: DbSession
) -> dict[str, bool]:
    conversation = _conversation(db, member.organization.id, conversation_id)
    marked = db.scalar(
        update(InboxConversation)
        .where(
            InboxConversation.id == conversation.id,
            InboxConversation.organization_id == member.organization.id,
            InboxConversation.updated_at == body.updated_at,
            InboxConversation.unread_count > 0,
        )
        .values(unread_count=0, updated_at=InboxConversation.updated_at)
        .returning(InboxConversation.id)
    )
    db.commit()
    return {"marked": marked is not None}


@router.patch("/{conversation_id}/unread")
def mark_inbox_unread(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> dict[str, int]:
    row = _conversation(db, member.organization.id, conversation_id)
    inbound = db.scalar(
        select(InboxMessage.id).where(
            InboxMessage.organization_id == row.organization_id,
            InboxMessage.conversation_id == row.id,
            InboxMessage.direction == "inbound",
        )
    )
    if inbound is None:
        raise AppError(409, "customer_message_missing", "There is no customer message to mark unread")
    if row.unread_count < 1:
        db.execute(
            update(InboxConversation)
            .where(
                InboxConversation.id == row.id,
                InboxConversation.organization_id == member.organization.id,
            )
            .values(unread_count=1, updated_at=InboxConversation.updated_at)
        )
    db.commit()
    db.refresh(row)
    return {"unread_count": row.unread_count}


@router.post("/{conversation_id}/archive")
def archive_conversation(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    if row.archived_at is None:
        row.archived_at = datetime.now(UTC)
        row.archived_by = member.user.id
    db.commit()
    return {"archived_at": row.archived_at}


@router.post("/{conversation_id}/restore")
def restore_conversation(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    row.archived_at = None
    row.archived_by = None
    db.commit()
    return {"archived_at": None}


@router.post("/{conversation_id}/draft")
def save_draft(
    conversation_id: uuid.UUID, body: MessageBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    if body.subject:
        row.subject = body.subject
    msg = InboxMessage(
        organization_id=member.organization.id,
        conversation_id=row.id,
        sender="draft",
        recipient=body.recipient,
        body=body.body,
        direction="outbound",
        channel=row.channel,
        delivery_status="draft",
        provider_message_id=f"draft-{uuid.uuid4()}",
    )
    db.add(msg)
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "delivery_status": msg.delivery_status}


@router.post("/{conversation_id}/draft-with-ai")
def draft_with_ai(
    conversation_id: uuid.UUID, body: AiReplyBody, member: CsrfMember, db: DbSession
) -> dict[str, str]:
    row = _conversation(db, member.organization.id, conversation_id)
    messages = db.scalars(
        select(InboxMessage)
        .where(InboxMessage.conversation_id == row.id)
        .order_by(InboxMessage.created_at)
    ).all()
    latest_inbound = next(
        (message for message in reversed(messages) if message.direction == "inbound"), None
    )
    handoff_reason = (
        _human_request_reason(latest_inbound.body)
        if latest_inbound
        and (row.handoff_resolved_at is None or latest_inbound.created_at > row.handoff_resolved_at)
        else None
    )
    if handoff_reason:
        row.handoff_requested = True
        row.handoff_reason = handoff_reason
        row.status = InboxStatus.pending
        db.commit()
    context = "\n".join(f"{message.direction}: {message.body}" for message in messages[-12:])
    crm_context = ""
    if row.contact_id:
        contact = db.scalar(
            select(Contact).where(
                Contact.id == row.contact_id, Contact.organization_id == member.organization.id
            )
        )
        if contact:
            crm_context += (
                f"\nContact: {contact.full_name}; email: {contact.email or 'none'}; "
                f"title: {contact.title or 'none'}"
            )
    if row.lead_id:
        lead = db.scalar(
            select(Lead).where(
                Lead.id == row.lead_id, Lead.organization_id == member.organization.id
            )
        )
        if lead:
            crm_context += (
                f"\nLead: {lead.title}; stage: {lead.status.value}; notes: {lead.notes or 'none'}"
            )
    knowledge_context = ""
    try:
        hits = search_chunks(
            db,
            member.organization.id,
            f"{row.subject} {body.instruction}",
            get_embedding_client(db, member.organization.id),
            limit=3,
        )
        knowledge_context = "\n".join(f"{hit.document_title}: {hit.content}" for hit in hits)
    except Exception:
        knowledge_context = ""
    try:
        result = get_chat_client(db, member.organization.id).complete(
            _configured_system(
                db,
                member.organization.id,
                "Draft a concise, factual customer email. Return JSON with subject and body. "
                "Never invent facts not supported by the conversation or organization context.",
            ),
            (
                f"Subject: {row.subject}\nCRM context:{crm_context}\n"
                f"Knowledge:\n{knowledge_context}"
                f"\nConversation:\n{context}"
                f"\nInstruction: {body.instruction}"
            ),
        )
        import json

        parsed = json.loads(result)
        return {
            "subject": str(parsed.get("subject") or row.subject),
            "body": str(parsed.get("body") or ""),
        }
    except Exception as exc:
        raise AppError(
            502, "inbox_ai_draft_failed", "The assistant could not draft a reply"
        ) from exc


@router.post("/{conversation_id}/submit-for-approval")
def submit_for_approval(
    conversation_id: uuid.UUID, body: MessageBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    reply_mode = _whatsapp_reply_mode(db, row)
    template = body.template_name.strip() if isinstance(body.template_name, str) else ""
    if reply_mode == "test" and template:
        raise AppError(
            409,
            "whatsapp_template_unavailable",
            "A restricted test reply cannot use a WhatsApp template",
        )
    if reason := _whatsapp_reply_unavailable(db, row):
        raise AppError(409, "whatsapp_reply_unavailable", reason)
    if row.lead_id is None:
        raise AppError(
            422,
            "approval_requires_lead",
            "Link this conversation to a CRM lead before requesting approval",
        )
    lead = db.scalar(
        select(Lead).where(Lead.id == row.lead_id, Lead.organization_id == member.organization.id)
    )
    inquiry = (
        db.scalar(
            select(Inquiry).where(
                Inquiry.organization_id == member.organization.id, Inquiry.lead_id == lead.id
            )
        )
        if lead
        else None
    )
    contact = (
        db.scalar(
            select(Contact).where(
                Contact.id == row.contact_id, Contact.organization_id == member.organization.id
            )
        )
        if row.contact_id
        else None
    )
    expected_recipient = (
        (contact.email if row.channel == "email" else contact.phone) if contact else None
    )
    if lead is None or inquiry is None or contact is None or expected_recipient != body.recipient:
        raise AppError(
            422,
            "recipient_not_owned",
            "The reply recipient must be the linked organization contact",
        )
    latest_inbound = db.scalar(
        select(InboxMessage.created_at)
        .where(InboxMessage.conversation_id == row.id, InboxMessage.direction == "inbound")
        .order_by(InboxMessage.created_at.desc())
    )
    run = AgentRun(
        organization_id=member.organization.id,
        inquiry_id=inquiry.id,
        started_by=member.user.id,
        status=RunStatus.awaiting_approval,
        origin=lead.origin,
    )
    db.add(run)
    db.flush()
    approval = create_approval(
        db,
        organization_id=member.organization.id,
        run_id=run.id,
        requested_by=member.user.id,
        action_type=ActionType.prepare_customer_response,
        payload={
            "conversation_id": str(row.id),
            "lead_id": str(lead.id),
            "contact_id": str(contact.id),
            "recipient": expected_recipient,
            "to": expected_recipient,
            "recipient_snapshot": expected_recipient,
            "channel": row.channel,
            "subject": body.subject or row.subject,
            "body": body.body,
            "template_name": template or None,
            "template_language": body.template_language,
            **({"whatsapp_delivery": reply_mode} if row.channel == "whatsapp" else {}),
            "last_inbound_at": latest_inbound.isoformat() if latest_inbound else None,
        },
        position=0,
    )
    return {"approval_id": str(approval.id), "status": "pending"}


class AssignmentBody(BaseModel):
    user_id: uuid.UUID | None = None


@router.get("/assignees")
def inbox_assignees(member: Member, db: DbSession) -> list[dict[str, object]]:
    return [
        {"user_id": user.id, "full_name": user.full_name, "email": user.email}
        for membership, user in list_team(db, member.organization.id)
        if user.is_active
    ]


@router.patch("/{conversation_id}/assignment")
def assign_inbox(
    conversation_id: uuid.UUID, body: AssignmentBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    if body.user_id is not None:
        user = db.scalar(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == body.user_id,
                Membership.organization_id == member.organization.id,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise AppError(
                404, "assignee_not_found", "Assignee is not an active organization member"
            )
    row.assigned_to = body.user_id
    db.commit()
    return {"assigned_to": row.assigned_to}


@router.post("/{conversation_id}/takeover")
def take_over_inbox(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    row.assigned_to = member.user.id
    row.handoff_requested = True
    row.handoff_accepted_at = datetime.now(UTC)
    row.ai_resumed = False
    row.status = InboxStatus.pending
    db.commit()
    return {"assigned_to": row.assigned_to, "handoff_requested": True, "ai_active": False}


@router.post("/{conversation_id}/resolve")
def resolve_inbox_handoff(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    if row.assigned_to != member.user.id and str(member.membership.role) not in {
        "admin",
        "MembershipRole.admin",
    }:
        raise AppError(
            403,
            "handoff_not_assigned",
            "Only the assigned staff member or an admin can resolve this handoff",
        )
    row.handoff_resolved_at = datetime.now(UTC)
    row.handoff_requested = False
    row.status = InboxStatus.resolved
    row.ai_resumed = False
    db.commit()
    return {"status": row.status.value, "ai_active": False}


@router.post("/{conversation_id}/resume-ai")
def resume_inbox_ai(
    conversation_id: uuid.UUID, member: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    widget = db.scalar(
        select(WidgetConfig)
        .join(WidgetSession, WidgetSession.widget_id == WidgetConfig.id)
        .where(
            WidgetSession.conversation_id == row.id,
            WidgetConfig.organization_id == member.organization.id,
        )
    )
    if widget is None or widget.operating_mode != "ai_auto_reply":
        raise AppError(
            409, "ai_not_enabled", "Automatic replies are not enabled for this website chat"
        )
    row.handoff_requested = False
    row.handoff_reason = None
    row.ai_resumed = True
    row.status = InboxStatus.open
    db.commit()
    return {"status": row.status.value, "ai_active": True}


class StaffMessageBody(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    client_message_id: str | None = Field(default=None, max_length=120)


@router.post("/{conversation_id}/staff-message")
def send_staff_message(
    conversation_id: uuid.UUID,
    body: StaffMessageBody,
    member: CsrfMember,
    db: DbSession,
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    if row.channel != "webchat":
        raise AppError(
            422,
            "invalid_channel",
            "Staff chat messages are only available for website conversations",
        )
    if row.assigned_to not in {None, member.user.id} and str(member.membership.role) not in {
        "admin",
        "MembershipRole.admin",
    }:
        raise AppError(
            403,
            "conversation_not_assigned",
            "This conversation is assigned to another staff member",
        )
    provider_id = f"staff-webchat-{body.client_message_id or uuid.uuid4()}"
    existing = db.scalar(
        select(InboxMessage).where(
            InboxMessage.organization_id == member.organization.id,
            InboxMessage.provider_message_id == provider_id,
        )
    )
    if existing is not None:
        return {"id": existing.id, "status": "duplicate"}
    message = InboxMessage(
        organization_id=member.organization.id,
        conversation_id=row.id,
        sender=member.user.full_name,
        recipient="visitor",
        body=body.body,
        direction="outbound",
        channel="webchat",
        delivery_status="delivered",
        provider_message_id=provider_id,
    )
    db.add(message)
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(message)
    return {"id": message.id, "status": message.delivery_status}


class ContactLinkBody(BaseModel):
    contact_id: uuid.UUID


@router.patch("/{conversation_id}/contact")
def link_inbox_contact(
    conversation_id: uuid.UUID, body: ContactLinkBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    contact = db.scalar(
        select(Contact).where(
            Contact.id == body.contact_id, Contact.organization_id == member.organization.id
        )
    )
    if contact is None:
        raise AppError(404, "contact_not_found", "Contact not found")
    row.contact_id = contact.id
    if row.lead_id is not None:
        lead = crm.get_lead(db, member.organization.id, row.lead_id)
        if lead.contact_id != contact.id:
            row.lead_id = None
    db.commit()
    return {"contact_id": row.contact_id}


class ContactCreateBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)


class LeadLinkBody(BaseModel):
    lead_id: uuid.UUID


@router.patch("/{conversation_id}/lead")
def link_inbox_lead(
    conversation_id: uuid.UUID, body: LeadLinkBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    lead = crm.get_lead(db, member.organization.id, body.lead_id)
    if lead.archived_at is not None or lead.contact_id is None:
        raise AppError(422, "inbox_lead_requires_contact", "Choose an active lead with a contact")
    if row.contact_id is not None and row.contact_id != lead.contact_id:
        raise AppError(409, "inbox_contact_mismatch", "The lead belongs to a different contact")
    row.lead_id = lead.id
    row.contact_id = lead.contact_id
    db.commit()
    return {"lead_id": row.lead_id, "contact_id": row.contact_id}


@router.post("/{conversation_id}/contact", status_code=201)
def create_inbox_contact(
    conversation_id: uuid.UUID, body: ContactCreateBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    phone = normalize_phone(body.phone) if body.phone else None
    if (row.channel == "whatsapp" and not phone) or (row.channel != "whatsapp" and not body.email):
        raise AppError(
            422, "contact_address_required", "Enter an address for the conversation channel"
        )
    contact = crm.create_contact(
        db,
        member.organization.id,
        ContactCreate(full_name=body.full_name, email=body.email, phone=phone).model_dump(),
    )
    row.contact_id = contact.id
    db.commit()
    return {"contact_id": contact.id}


class IntakeBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.post("/{conversation_id}/crm-intake")
def record_crm_intake(
    conversation_id: uuid.UUID, body: IntakeBody, member: CsrfMember, db: DbSession
) -> dict[str, uuid.UUID]:
    org = member.organization.id
    row = _conversation(db, org, conversation_id, lock=True)
    title = body.title.strip()
    if not title:
        raise AppError(422, "intake_title_required", "Enter a lead title")
    if row.contact_id is None:
        raise AppError(409, "contact_required", "Link a contact before recording this inquiry")
    contact = crm.get_contact(db, org, row.contact_id)
    if contact.archived_at is not None:
        raise AppError(409, "contact_archived", "Choose an active contact")
    lead = crm.get_lead(db, org, row.lead_id) if row.lead_id else None
    if lead and (lead.archived_at is not None or lead.contact_id != contact.id):
        raise AppError(409, "invalid_inbox_lead", "Link an active lead for this contact")
    message = db.scalar(
        select(InboxMessage)
        .where(
            InboxMessage.organization_id == org,
            InboxMessage.conversation_id == row.id,
            InboxMessage.direction == "inbound",
        )
        .order_by(InboxMessage.created_at, InboxMessage.id)
        .limit(1)
    )
    if message is None:
        raise AppError(
            409,
            "customer_message_missing",
            "Wait for a customer message before recording an inquiry",
        )
    if lead is None:
        lead = crm.create_lead(
            db,
            org,
            member.user.id,
            {
                "title": title,
                "status": LeadStatus.new,
                "source": row.channel,
                "company_id": contact.company_id,
                "contact_id": contact.id,
            },
            commit=False,
        )
        row.lead_id = lead.id
        stage_lead_created(db, org, lead.id, None)
    inquiry = db.scalar(
        select(Inquiry)
        .where(
            Inquiry.organization_id == org,
            Inquiry.lead_id == lead.id,
            Inquiry.archived_at.is_(None),
        )
        .order_by(Inquiry.created_at.desc(), Inquiry.id)
        .limit(1)
    )
    if inquiry is None:
        inquiry = crm.create_inquiry(
            db,
            org,
            {
                "lead_id": lead.id,
                "company_id": contact.company_id,
                "subject": row.subject,
                "body": message.body[:8000],
            },
            commit=False,
        )
    db.commit()
    return {"lead_id": lead.id, "inquiry_id": inquiry.id}


def _whatsapp_reply_unavailable(db: Session, row: InboxConversation) -> str | None:
    return _whatsapp_reply_state(db, row)[1]


def _whatsapp_reply_mode(db: Session, row: InboxConversation) -> str | None:
    return _whatsapp_reply_state(db, row)[0]


def _whatsapp_reply_state(db: Session, row: InboxConversation) -> tuple[str | None, str | None]:
    from app.domains.integrations.whatsapp_test import whatsapp_reply_availability

    return whatsapp_reply_availability(db, row)


@router.patch("/{conversation_id}/status")
def update_status(
    conversation_id: uuid.UUID, status: str, member: CsrfMember, db: DbSession
) -> dict[str, str]:
    row = _conversation(db, member.organization.id, conversation_id)
    if status not in {item.value for item in InboxStatus}:
        raise AppError(422, "invalid_status", "Invalid conversation status")
    row.status = InboxStatus(status)
    db.commit()
    return {"status": status}


@router.post("/webhooks/inbound")
async def inbound(request: Request, db: DbSession) -> dict[str, object]:
    try:
        org_id = uuid.UUID(str(request.path_params["organization_id"]))
    except ValueError:
        raise AppError(404, "workspace_not_found", "Workspace not found") from None
    settings = get_settings()
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > settings.webhook_max_bytes:
            raise AppError(413, "inbound_message_too_large", "Inbound message is too large")
        body.extend(chunk)
    secret = settings.inbox_webhook_secret
    timestamp = request.headers.get("x-atlas-inbox-timestamp", "")
    signature = request.headers.get("x-atlas-inbox-signature", "")
    if (
        not secret
        or not re.fullmatch(r"[0-9]{1,12}", timestamp)
        or len(signature) != 64
        or not signature.isascii()
        or abs(datetime.now(UTC).timestamp() - int(timestamp)) > settings.webhook_skew_seconds
    ):
        raise AppError(400, "invalid_webhook_signature", "Inbound signature is invalid")
    expected = hmac.new(
        secret.encode(), f"v1.{org_id}.{timestamp}.".encode() + body, hashlib.sha256
    )
    if not hmac.compare_digest(signature, expected.hexdigest()):
        raise AppError(400, "invalid_webhook_signature", "Inbound signature is invalid")
    try:
        event = InboundBody.model_validate_json(body)
    except ValidationError:
        raise AppError(
            422, "invalid_inbound_message", "Inbound message fields are invalid"
        ) from None
    return await run_in_threadpool(_record_inbound_email, db, org_id, event)


def _record_inbound_email(
    db: DbSession, org_id: uuid.UUID, event: InboundBody
) -> dict[str, object]:
    # Serialize delivery and threading for this tenant, including simultaneous retries.
    if (
        db.scalar(select(Organization.id).where(Organization.id == org_id).with_for_update())
        is None
    ):
        raise AppError(404, "workspace_not_found", "Workspace not found")
    if (
        db.scalar(
            select(InboxMessage).where(
                InboxMessage.organization_id == org_id,
                InboxMessage.provider_message_id == event.message_id,
            )
        )
        is not None
    ):
        return {"status": "duplicate"}
    sender, recipient = event.sender.casefold(), event.recipient.casefold()
    matches = db.scalars(
        select(Contact)
        .where(
            Contact.organization_id == org_id,
            func.lower(Contact.email) == sender,
            Contact.archived_at.is_(None),
        )
        .limit(2)
    ).all()
    contact = matches[0] if len(matches) == 1 else None
    subject = (
        re.sub(r"^(?:re:\s*)+", "", event.subject.strip(), flags=re.IGNORECASE) or event.subject
    )
    matching_mailbox = (
        select(InboxMessage.id)
        .where(
            InboxMessage.conversation_id == InboxConversation.id,
            InboxMessage.organization_id == org_id,
            InboxMessage.channel == "email",
            InboxMessage.direction == "inbound",
            InboxMessage.sender == sender,
            InboxMessage.recipient == recipient,
        )
        .exists()
    )
    conversation = db.scalar(
        select(InboxConversation)
        .where(
            InboxConversation.organization_id == org_id,
            InboxConversation.channel == "email",
            InboxConversation.status != InboxStatus.resolved,
            func.lower(InboxConversation.subject) == subject.casefold(),
            matching_mailbox,
        )
        .order_by(InboxConversation.updated_at.desc(), InboxConversation.id)
        .limit(1)
        .with_for_update()
    )
    if conversation is None:
        conversation = InboxConversation(
            organization_id=org_id,
            contact_id=contact.id if contact else None,
            subject=subject,
            status=InboxStatus.open,
            unread_count=0,
            channel=event.channel,
        )
        db.add(conversation)
        db.flush()
    db.add(
        InboxMessage(
            organization_id=org_id,
            conversation_id=conversation.id,
            sender=sender,
            recipient=recipient,
            body=event.body,
            direction="inbound",
            channel=event.channel,
            delivery_status="received",
            provider_message_id=event.message_id,
        )
    )
    _register_inbound(conversation, event.body)
    db.commit()
    return {
        "status": "accepted",
        "conversation_id": str(conversation.id),
        "matched_contact": contact is not None,
    }


@router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(request: Request) -> PlainTextResponse:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    settings = get_settings()
    verify_token = settings.whatsapp_webhook_verify_token or settings.inbox_webhook_secret
    if (
        mode != "subscribe"
        or not token
        or not challenge
        or not hmac.compare_digest(token.encode(), verify_token.encode())
    ):
        raise AppError(403, "invalid_webhook_verification", "Webhook verification failed")
    return PlainTextResponse(challenge)


def _webhook_objects(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    organization_id: uuid.UUID, request: Request, db: DbSession
) -> dict[str, object]:
    settings = get_settings()
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > settings.webhook_max_bytes:
            raise AppError(413, "payload_too_large", "Webhook payload is too large")
        raw.extend(chunk)
    signature = request.headers.get("x-hub-signature-256", "")
    secret = settings.whatsapp_webhook_app_secret or settings.inbox_webhook_secret
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature.encode(), expected.encode()):
        raise AppError(400, "invalid_webhook_signature", "WhatsApp signature is invalid")
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(422, "invalid_whatsapp_payload", "WhatsApp payload must be JSON") from exc
    if not isinstance(document, dict):
        raise AppError(422, "invalid_whatsapp_payload", "WhatsApp payload must be a JSON object")

    # Serialize deliveries and disconnects for this workspace's single Meta account.
    integration = db.scalar(
        select(IntegrationConfig)
        .where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
            IntegrationConfig.status == IntegrationStatus.configured,
            IntegrationConfig.verified_at.is_not(None),
        )
        .with_for_update()
    )
    accepted = duplicates = 0
    if integration is None:
        return {"status": "accepted", "accepted": accepted, "duplicates": duplicates}
    phone_id = str(integration.config.get("phone_number_id", ""))
    account_id = integration.config.get("business_account_id")
    ambiguous_route = db.scalar(
        select(IntegrationConfig.id)
        .where(
            IntegrationConfig.organization_id != organization_id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
            IntegrationConfig.status == IntegrationStatus.configured,
            IntegrationConfig.verified_at.is_not(None),
            IntegrationConfig.config["phone_number_id"].as_string() == phone_id,
        )
        .limit(1)
    )
    if ambiguous_route is not None:
        raise AppError(
            409,
            "whatsapp_number_conflict",
            "The WhatsApp number has multiple workspace connections",
        )
    for entry in _webhook_objects(document.get("entry")):
        if not account_id or str(entry.get("id", "")) != account_id:
            continue
        for change in _webhook_objects(entry.get("changes")):
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict) or str(metadata.get("phone_number_id")) != phone_id:
                continue
            for item in _webhook_objects(value.get("messages")):
                if item.get("type") != "text":
                    continue
                message_id, sender, text_data = item.get("id"), item.get("from"), item.get("text")
                body = text_data.get("body") if isinstance(text_data, dict) else None
                if (
                    not isinstance(message_id, str)
                    or not 1 <= len(message_id) <= 200
                    or not isinstance(sender, str)
                    or not re.fullmatch(r"[0-9]{5,32}", sender)
                    or not isinstance(body, str)
                    or not 1 <= len(body.strip()) <= 10000
                ):
                    continue
                exists = db.scalar(
                    select(InboxMessage.id).where(
                        InboxMessage.organization_id == organization_id,
                        InboxMessage.provider_message_id == message_id,
                    )
                )
                if exists:
                    duplicates += 1
                    continue
                conversation = db.scalar(
                    select(InboxConversation)
                    .where(
                        InboxConversation.organization_id == organization_id,
                        InboxConversation.channel == "whatsapp",
                        select(InboxMessage.id)
                        .where(
                            InboxMessage.conversation_id == InboxConversation.id,
                            InboxMessage.organization_id == organization_id,
                            InboxMessage.direction == "inbound",
                            InboxMessage.channel == "whatsapp",
                            InboxMessage.sender == sender,
                            InboxMessage.recipient == phone_id,
                        )
                        .exists(),
                    )
                    .order_by(InboxConversation.updated_at.desc(), InboxConversation.id)
                    .limit(1)
                    .with_for_update()
                )
                if conversation is None:
                    contact_id = db.scalar(
                        select(Contact.id)
                        .where(
                            Contact.organization_id == organization_id,
                            Contact.archived_at.is_(None),
                            Contact.phone.in_([sender, "+" + sender]),
                        )
                        .order_by(Contact.id)
                        .limit(1)
                    )
                    conversation = InboxConversation(
                        organization_id=organization_id,
                        contact_id=contact_id,
                        subject="WhatsApp conversation",
                        status=InboxStatus.open,
                        unread_count=0,
                        channel="whatsapp",
                    )
                    db.add(conversation)
                    db.flush()
                if conversation.status == InboxStatus.resolved:
                    conversation.status = InboxStatus.open
                _register_inbound(conversation, body.strip())
                db.add(
                    InboxMessage(
                        organization_id=organization_id,
                        conversation_id=conversation.id,
                        sender=sender,
                        recipient=phone_id,
                        body=body.strip(),
                        direction="inbound",
                        channel="whatsapp",
                        delivery_status="received",
                        provider_message_id=message_id,
                    )
                )
                db.flush()
                accepted += 1
            for status in _webhook_objects(value.get("statuses")):
                provider_id, state = status.get("id"), status.get("status")
                if not isinstance(provider_id, str) or state not in (
                    "sent",
                    "delivered",
                    "read",
                    "failed",
                ):
                    continue
                message = db.scalar(
                    select(InboxMessage).where(
                        InboxMessage.provider_message_id == provider_id,
                        InboxMessage.organization_id == organization_id,
                        InboxMessage.channel == "whatsapp",
                        InboxMessage.direction == "outbound",
                    )
                )
                if message is not None:
                    priority = {"sent": 1, "failed": 2, "delivered": 3, "read": 4}
                    if priority[str(state)] > priority.get(message.delivery_status, 0):
                        message.delivery_status = str(state)
    db.commit()
    return {"status": "accepted", "accepted": accepted, "duplicates": duplicates}


class WidgetConfigBody(BaseModel):
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    welcome_message: str = Field(default="How can we help?", min_length=1, max_length=500)
    operating_mode: str = Field(
        default="human_review", pattern="^(human_review|ai_assist|ai_auto_reply)$"
    )
    enabled: bool | None = None


@router.put("/widget")
def save_widget_config(
    body: WidgetConfigBody, admin: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = db.scalar(
        select(WidgetConfig)
        .where(WidgetConfig.organization_id == admin.organization.id)
        .with_for_update()
    )
    if row is None:
        row = WidgetConfig(
            organization_id=admin.organization.id,
            public_id=secrets.token_urlsafe(18),
            allowed_domains=body.allowed_domains,
            welcome_message=body.welcome_message,
            operating_mode=body.operating_mode,
        )
        db.add(row)
    else:
        row.allowed_domains = body.allowed_domains
        row.welcome_message = body.welcome_message
        row.operating_mode = body.operating_mode
    if body.enabled is not None and row.enabled != body.enabled:
        row.enabled = body.enabled
        record_event(
            db,
            admin.organization.id,
            "website_chat_enabled" if body.enabled else "website_chat_disabled",
            {},
            actor_id=admin.user.id,
        )
    db.commit()
    return {
        "public_id": row.public_id,
        "allowed_domains": row.allowed_domains,
        "welcome_message": row.welcome_message,
        "operating_mode": row.operating_mode,
        "enabled": row.enabled,
    }


@router.get("/widget")
def get_widget_config(member: Member, db: DbSession) -> dict[str, object] | None:
    row = db.scalar(
        select(WidgetConfig).where(WidgetConfig.organization_id == member.organization.id)
    )
    if row is None:
        return None
    return {
        "public_id": row.public_id,
        "allowed_domains": row.allowed_domains,
        "welcome_message": row.welcome_message,
        "operating_mode": row.operating_mode,
        "enabled": row.enabled,
    }


def _widget(db: DbSession, public_id: str) -> WidgetConfig:
    row = db.scalar(
        select(WidgetConfig).where(
            WidgetConfig.public_id == public_id, WidgetConfig.enabled.is_(True)
        )
    )
    if row is None:
        raise AppError(404, "widget_not_found", "Chat widget not found")
    return row


def _widget_origin(widget: WidgetConfig, request: Request) -> str:
    origin = request.headers.get("origin") or f"{request.url.scheme}://{request.url.netloc}"
    if widget.allowed_domains and origin not in widget.allowed_domains:
        raise AppError(
            403, "widget_origin_denied", "This website is not allowed to use the chat widget"
        )
    return origin


def _widget_session(
    db: DbSession, widget: WidgetConfig, token: str, origin: str, *, lock: bool = False
) -> WidgetSession:
    query = select(WidgetSession).where(
        WidgetSession.widget_id == widget.id,
        WidgetSession.visitor_token_hash == hashlib.sha256(token.encode()).hexdigest(),
    )
    session = db.scalar(query.with_for_update() if lock else query)
    if session is None or (session.origin and session.origin != origin):
        raise AppError(401, "invalid_widget_session", "Chat session is invalid")
    return session


@public_widget_router.post("/{public_id}/sessions")
def create_widget_session(public_id: str, request: Request, db: DbSession) -> dict[str, object]:
    widget = _widget(db, public_id)
    origin = _widget_origin(widget, request)
    token = secrets.token_urlsafe(32)
    conversation = InboxConversation(
        organization_id=widget.organization_id,
        subject="Website chat",
        status=InboxStatus.open,
        unread_count=0,
        channel="webchat",
    )
    db.add(conversation)
    db.flush()
    session = WidgetSession(
        widget_id=widget.id,
        conversation_id=conversation.id,
        visitor_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        origin=origin,
    )
    db.add(session)
    db.commit()
    return {
        "session_token": token,
        "conversation_id": str(conversation.id),
        "welcome_message": widget.welcome_message,
    }


class WidgetMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    client_message_id: str | None = Field(default=None, max_length=120)


@public_widget_router.post("/{public_id}/sessions/{session_token}/messages")
def widget_message(
    public_id: str, session_token: str, body: WidgetMessageBody, request: Request, db: DbSession
) -> dict[str, str]:
    widget = _widget(db, public_id)
    origin = _widget_origin(widget, request)
    session = _widget_session(db, widget, session_token, origin, lock=True)
    client_id = body.client_message_id or str(uuid.uuid4())
    provider_id = f"webchat-{session.id}-{client_id}"
    existing = db.scalar(
        select(InboxMessage).where(
            InboxMessage.organization_id == widget.organization_id,
            InboxMessage.conversation_id == session.conversation_id,
            InboxMessage.provider_message_id.in_((provider_id, f"webchat-{client_id}")),
        )
    )
    if existing is not None:
        if existing.body != body.message:
            raise AppError(409, "widget_message_conflict", "This message ID has already been used")
        return {"status": "duplicate"}
    inbound = InboxMessage(
        organization_id=widget.organization_id,
        conversation_id=session.conversation_id,
        sender="visitor",
        recipient="ATLAS",
        body=body.message,
        direction="inbound",
        channel="webchat",
        delivery_status="received",
        provider_message_id=provider_id,
    )
    db.add(inbound)
    conversation = db.get(InboxConversation, session.conversation_id)
    if conversation is None:
        raise AppError(404, "conversation_not_found", "Chat conversation not found")
    _register_inbound(conversation, body.message)
    db.commit()
    if (
        widget.operating_mode == "ai_auto_reply"
        and not conversation.handoff_requested
        and conversation.status != InboxStatus.resolved
    ):
        try:
            result = evaluate_inbox_draft(
                db,
                widget.organization_id,
                conversation.id,
                body.message,
                get_embedding_client(db, widget.organization_id),
                get_chat_client(db, widget.organization_id),
            )
            if result["grounding"] == "grounded":
                draft = json.loads(str(result["response"]))
                reply = draft.get("body") if isinstance(draft, dict) else None
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError("The generated reply is empty")
                db.add(
                    InboxMessage(
                        organization_id=widget.organization_id,
                        conversation_id=conversation.id,
                        sender="ATLAS AI",
                        recipient="visitor",
                        body=reply.strip()[:10000],
                        direction="outbound",
                        channel="webchat",
                        delivery_status="delivered",
                        provider_message_id=f"webchat-ai-{inbound.id}",
                    )
                )
            else:
                conversation.handoff_requested = True
                conversation.handoff_reason = str(
                    result.get("reason") or "AI could not answer safely"
                )
                conversation.status = InboxStatus.pending
            db.commit()
        except Exception:
            db.rollback()
            conversation.handoff_requested = True
            conversation.handoff_reason = "AI service unavailable"
            conversation.status = InboxStatus.pending
            db.commit()
    return {"status": "accepted"}


@public_widget_router.get("/{public_id}/sessions/{session_token}/messages")
def widget_messages(
    public_id: str, session_token: str, request: Request, db: DbSession
) -> list[dict[str, object]]:
    widget = _widget(db, public_id)
    session = _widget_session(db, widget, session_token, _widget_origin(widget, request))
    messages = db.scalars(
        select(InboxMessage)
        .where(InboxMessage.conversation_id == session.conversation_id)
        .order_by(InboxMessage.created_at, InboxMessage.id)
    ).all()
    return [
        {
            "body": message.body,
            "direction": message.direction,
            "sender": message.sender,
            "delivery_status": message.delivery_status,
            "created_at": message.created_at,
        }
        for message in messages
    ]
