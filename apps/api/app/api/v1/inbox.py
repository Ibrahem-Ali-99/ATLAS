# ruff: noqa: E501
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType
from app.domains.approvals.service import create_approval
from app.domains.assistant.service import _configured_system
from app.domains.crm import service as crm
from app.domains.crm.models import Contact, Inquiry, Lead
from app.domains.crm.schemas import ContactCreate
from app.domains.identity.dependencies import CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.identity.models import Membership, User
from app.domains.identity.service import list_team
from app.domains.inbox.models import (
    InboxConversation,
    InboxMessage,
    InboxStatus,
    WidgetConfig,
    WidgetSession,
)
from app.domains.integrations.models import IntegrationConfig, IntegrationType
from app.domains.knowledge.retrieval import search_chunks
from app.integrations.language import get_chat_client, get_embedding_client

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
    sender: str = Field(min_length=3, max_length=320)
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    channel: str = Field(default="email", pattern="^(email|whatsapp)$")


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
            select(Contact).where(Contact.id == row.contact_id, Contact.organization_id == organization_id)
        )
        if contact:
            crm_context.append(f"Contact: {contact.full_name}; title: {contact.title or 'none'}")
    if row.lead_id:
        lead = db.scalar(select(Lead).where(Lead.id == row.lead_id, Lead.organization_id == organization_id))
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


def _conversation(db: DbSession, org: uuid.UUID, conversation_id: uuid.UUID) -> InboxConversation:
    row = db.scalar(
        select(InboxConversation).where(
            InboxConversation.id == conversation_id, InboxConversation.organization_id == org
        )
    )
    if row is None:
        raise AppError(404, "conversation_not_found", "Conversation not found")
    return row


@router.get("")
def list_inbox(
    member: Member, db: DbSession, q: str | None = None, assigned: str = "all", channel: str = "all"
) -> list[dict[str, object]]:
    query = (
        select(InboxConversation)
        .where(InboxConversation.organization_id == member.organization.id)
        .order_by(InboxConversation.updated_at.desc())
    )
    rows = list(db.scalars(query))
    if assigned == "assigned":
        rows = [row for row in rows if row.assigned_to is not None]
    elif assigned == "unassigned":
        rows = [row for row in rows if row.assigned_to is None]
    if channel != "all":
        rows = [row for row in rows if row.channel == channel]
    if q:
        rows = [row for row in rows if q.lower() in row.subject.lower()]
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
            "handoff_requested": row.handoff_requested,
            "handoff_reason": row.handoff_reason,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.get("/{conversation_id}")
def get_inbox(conversation_id: uuid.UUID, member: Member, db: DbSession) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    messages = db.scalars(
        select(InboxMessage)
        .where(InboxMessage.conversation_id == row.id)
        .order_by(InboxMessage.created_at)
    ).all()
    row.unread_count = 0
    latest_inbound = next((message for message in reversed(messages) if message.direction == "inbound"), None)
    handoff_reason = _human_request_reason(latest_inbound.body) if latest_inbound else None
    if handoff_reason:
        row.handoff_requested = True
        row.handoff_reason = handoff_reason
        row.status = InboxStatus.pending
    db.commit()
    return {
        "id": row.id,
        "subject": row.subject,
        "channel": row.channel,
        "status": row.status.value,
        "unread_count": row.unread_count,
        "contact_id": row.contact_id,
        "lead_id": row.lead_id,
        "assigned_to": row.assigned_to,
        "handoff_requested": row.handoff_requested,
        "handoff_reason": row.handoff_reason,
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
    row.updated_at = datetime.utcnow()
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
    latest_inbound = next((message for message in reversed(messages) if message.direction == "inbound"), None)
    handoff_reason = _human_request_reason(latest_inbound.body) if latest_inbound else None
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
            "template_name": body.template_name,
            "template_language": body.template_language,
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
    row.handoff_accepted_at = datetime.utcnow()
    row.ai_resumed = False
    row.status = InboxStatus.pending
    db.commit()
    return {"assigned_to": row.assigned_to, "handoff_requested": True, "ai_active": False}


@router.post("/{conversation_id}/resolve")
def resolve_inbox_handoff(
    conversation_id: uuid.UUID, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    if row.assigned_to != member.user.id and str(member.membership.role) not in {"admin", "MembershipRole.admin"}:
        raise AppError(403, "handoff_not_assigned", "Only the assigned staff member or an admin can resolve this handoff")
    row.handoff_resolved_at = datetime.utcnow()
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
        select(WidgetConfig).join(WidgetSession, WidgetSession.widget_id == WidgetConfig.id).where(
            WidgetSession.conversation_id == row.id,
            WidgetConfig.organization_id == member.organization.id,
        )
    )
    if widget is None or widget.operating_mode != "ai_auto_reply":
        raise AppError(409, "ai_not_enabled", "Automatic replies are not enabled for this website chat")
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
        raise AppError(422, "invalid_channel", "Staff chat messages are only available for website conversations")
    if row.assigned_to not in {None, member.user.id} and str(member.membership.role) not in {"admin", "MembershipRole.admin"}:
        raise AppError(403, "conversation_not_assigned", "This conversation is assigned to another staff member")
    provider_id = f"staff-webchat-{body.client_message_id or uuid.uuid4()}"
    existing = db.scalar(select(InboxMessage).where(InboxMessage.organization_id == member.organization.id, InboxMessage.provider_message_id == provider_id))
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
    row.updated_at = datetime.utcnow()
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
    db.commit()
    return {"contact_id": row.contact_id}


class ContactCreateBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)


@router.post("/{conversation_id}/contact", status_code=201)
def create_inbox_contact(
    conversation_id: uuid.UUID, body: ContactCreateBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    row = _conversation(db, member.organization.id, conversation_id)
    contact = crm.create_contact(
        db,
        member.organization.id,
        ContactCreate(full_name=body.full_name, email=body.email).model_dump(),
    )
    row.contact_id = contact.id
    db.commit()
    return {"contact_id": contact.id}


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
    org_id = uuid.UUID(str(request.path_params["organization_id"]))
    body = await request.body()
    secret = get_settings().inbox_webhook_secret
    signature = request.headers.get("x-atlas-inbox-signature", "")
    if not secret or not hmac.compare_digest(
        signature, hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    ):
        raise AppError(400, "invalid_webhook_signature", "Inbound signature is invalid")
    event = InboundBody.model_validate_json(body)
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
    contact = db.scalar(
        select(Contact).where(
            Contact.organization_id == org_id, Contact.email == event.sender.lower()
        )
    )
    conversation = None
    if contact is not None:
        conversation = db.scalar(
            select(InboxConversation).where(
                InboxConversation.organization_id == org_id,
                InboxConversation.contact_id == contact.id,
                InboxConversation.status != InboxStatus.resolved,
            )
        )
    if conversation is None:
        conversation = InboxConversation(
            organization_id=org_id,
            contact_id=contact.id if contact else None,
            subject=event.subject,
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
            sender=event.sender.lower(),
            recipient=event.recipient,
            body=event.body,
            direction="inbound",
            channel=event.channel,
            delivery_status="received",
            provider_message_id=event.message_id,
        )
    )
    conversation.unread_count += 1
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
    if (
        mode != "subscribe"
        or not token
        or not challenge
        or not hmac.compare_digest(token, get_settings().inbox_webhook_secret)
    ):
        raise AppError(403, "invalid_webhook_verification", "Webhook verification failed")
    return PlainTextResponse(challenge)


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: DbSession) -> dict[str, object]:
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    secret = get_settings().inbox_webhook_secret
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature, expected):
        raise AppError(400, "invalid_webhook_signature", "WhatsApp signature is invalid")
    document = json.loads(raw)
    accepted = 0
    duplicates = 0
    for entry in document.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_id = value.get("metadata", {}).get("phone_number_id")
            integration = db.scalar(
                select(IntegrationConfig).where(
                    IntegrationConfig.integration_type == IntegrationType.whatsapp,
                    IntegrationConfig.config["phone_number_id"].as_string() == phone_id,
                )
            )
            if integration is None:
                continue
            for item in value.get("messages", []):
                if item.get("type") != "text" or not item.get("id"):
                    continue
                message_id = str(item["id"])
                if db.scalar(
                    select(InboxMessage.id).where(
                        InboxMessage.organization_id == integration.organization_id,
                        InboxMessage.provider_message_id == message_id,
                    )
                ):
                    duplicates += 1
                    continue
                sender = str(item.get("from", "")).strip()
                text = str(item.get("text", {}).get("body", "")).strip()
                if not sender or not text:
                    continue
                contact = db.scalar(
                    select(Contact).where(
                        Contact.organization_id == integration.organization_id,
                        Contact.phone == sender,
                    )
                )
                conversation = InboxConversation(
                    organization_id=integration.organization_id,
                    contact_id=contact.id if contact else None,
                    subject="WhatsApp conversation",
                    status=InboxStatus.open,
                    unread_count=1,
                    channel="whatsapp",
                )
                db.add(conversation)
                db.flush()
                db.add(
                    InboxMessage(
                        organization_id=integration.organization_id,
                        conversation_id=conversation.id,
                        sender=sender,
                        recipient=str(phone_id),
                        body=text,
                        direction="inbound",
                        channel="whatsapp",
                        delivery_status="received",
                        provider_message_id=message_id,
                    )
                )
                accepted += 1
            for status in value.get("statuses", []):
                provider_id = str(status.get("id", ""))
                if not provider_id:
                    continue
                message = db.scalar(
                    select(InboxMessage).where(
                        InboxMessage.provider_message_id == provider_id,
                        InboxMessage.organization_id == integration.organization_id,
                    )
                )
                if message is not None:
                    message.delivery_status = str(status.get("status", "unknown"))[:24]
    db.commit()
    return {"status": "accepted", "accepted": accepted, "duplicates": duplicates}


class WidgetConfigBody(BaseModel):
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    welcome_message: str = Field(default="How can we help?", min_length=1, max_length=500)
    operating_mode: str = Field(
        default="human_review", pattern="^(human_review|ai_assist|ai_auto_reply)$"
    )


@router.put("/widget")
def save_widget_config(
    body: WidgetConfigBody, admin: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = db.scalar(
        select(WidgetConfig).where(WidgetConfig.organization_id == admin.organization.id)
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


@public_widget_router.post("/{public_id}/sessions")
def create_widget_session(public_id: str, request: Request, db: DbSession) -> dict[str, object]:
    widget = _widget(db, public_id)
    origin = request.headers.get("origin", "")
    if widget.allowed_domains and origin not in widget.allowed_domains:
        raise AppError(
            403, "widget_origin_denied", "This website is not allowed to use the chat widget"
        )
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
    origin = request.headers.get("origin", "")
    if widget.allowed_domains and origin not in widget.allowed_domains:
        raise AppError(
            403, "widget_origin_denied", "This website is not allowed to use the chat widget"
        )
    session = db.scalar(
        select(WidgetSession).where(
            WidgetSession.widget_id == widget.id,
            WidgetSession.visitor_token_hash == hashlib.sha256(session_token.encode()).hexdigest(),
        )
    )
    if session is None:
        raise AppError(401, "invalid_widget_session", "Chat session is invalid")
    provider_id = f"webchat-{body.client_message_id}" if body.client_message_id else f"webchat-{uuid.uuid4()}"
    existing = db.scalar(
        select(InboxMessage).where(
            InboxMessage.organization_id == widget.organization_id,
            InboxMessage.provider_message_id == provider_id,
        )
    )
    if existing is not None:
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
    conversation.unread_count += 1
    conversation.updated_at = datetime.utcnow()
    db.commit()
    if widget.operating_mode == "ai_auto_reply" and not conversation.handoff_requested:
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
                db.add(
                    InboxMessage(
                        organization_id=widget.organization_id,
                        conversation_id=conversation.id,
                        sender="ATLAS AI",
                        recipient="visitor",
                        body=str(result["response"]),
                        direction="outbound",
                        channel="webchat",
                        delivery_status="delivered",
                        provider_message_id=f"webchat-ai-{inbound.id}",
                    )
                )
            else:
                conversation.handoff_requested = True
                conversation.handoff_reason = str(result.get("reason") or "AI could not answer safely")
                conversation.status = InboxStatus.pending
            db.commit()
        except Exception:
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
    origin = request.headers.get("origin", "")
    if widget.allowed_domains and origin not in widget.allowed_domains:
        raise AppError(
            403, "widget_origin_denied", "This website is not allowed to use the chat widget"
        )
    session = db.scalar(
        select(WidgetSession).where(
            WidgetSession.widget_id == widget.id,
            WidgetSession.visitor_token_hash == hashlib.sha256(session_token.encode()).hexdigest(),
        )
    )
    if session is None:
        raise AppError(401, "invalid_widget_session", "Chat session is invalid")
    messages = db.scalars(
        select(InboxMessage)
        .where(InboxMessage.conversation_id == session.conversation_id)
        .order_by(InboxMessage.created_at)
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
