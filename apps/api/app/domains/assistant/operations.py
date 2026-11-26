# ruff: noqa: E501
"""Customer summaries and business proposals built only from stored records.

A proposal is not an execution. Follow-ups and appointments become approvals.
A task is created only after the member confirms it.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, Approval
from app.domains.approvals.service import create_approval
from app.domains.assistant.catalog import ReadAnswer
from app.domains.assistant.models import AssistantProposal, Conversation, Message
from app.domains.assistant.routing import Intent
from app.domains.assistant.schemas import ProposalOut
from app.domains.automation.models import WorkflowTask
from app.domains.crm import service as crm
from app.domains.crm.models import Company, Contact, Inquiry, Lead, LeadStatus
from app.domains.inbox.models import InboxConversation, InboxMessage

_NAME = re.compile(r"\b(?:for|about|with)\s+(.+)$", re.IGNORECASE)
_SUMMARY_NAME = re.compile(
    r"\bsummar(?:y|ize|ise)\s+(?:the\s+)?(?:lead|customer|contact)\s+(.+)$",
    re.IGNORECASE,
)
_LEADING_KIND = re.compile(r"^(?:the\s+)?(?:lead|customer|contact)\s+", re.IGNORECASE)
_OPEN_LEAD = re.compile(
    r"^(?:the\s+|an?\s+)?(?:first|next|earliest|top)\s+(?:open\s+|qualified\s+|new\s+)?"
    r"(?:lead|customer)$|^(?:an?\s+)?open\s+lead$|^(?:that|this)(?:\s+same)?\s+lead$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProposalDraft:
    kind: str
    title: str
    summary: str
    payload: dict[str, Any]


def question_for_stored_lead(
    db: Session,
    organization_id: uuid.UUID,
    question: str,
    conversation_id: uuid.UUID | None = None,
) -> str:
    """Replace 'the first open lead' with a stored title. A real name is left as written."""

    name = requested_name(question)
    if name is None or _OPEN_LEAD.search(name.strip()) is None:
        return question
    title = None
    if conversation_id is not None and re.search(r"\b(that|this|same)\b", name, re.IGNORECASE):
        title = _recent_proposed_lead(db, organization_id, conversation_id)
    if title is None:
        title = _priority_lead_title(db, organization_id)
    if title is None:
        return question
    start = question.lower().rfind(name.lower())
    if start < 0:
        return question
    return question[:start] + title


def _recent_proposed_lead(
    db: Session, organization_id: uuid.UUID, conversation_id: uuid.UUID
) -> str | None:
    rows = db.scalars(
        select(AssistantProposal)
        .where(
            AssistantProposal.organization_id == organization_id,
            AssistantProposal.conversation_id == conversation_id,
        )
        .order_by(AssistantProposal.created_at.desc())
        .limit(5)
    ).all()
    for proposal in rows:
        raw = proposal.payload.get("lead_id") if isinstance(proposal.payload, dict) else None
        if not isinstance(raw, str):
            continue
        try:
            lead_id = uuid.UUID(raw)
        except ValueError:
            continue
        lead = db.get(Lead, lead_id)
        if lead is not None and lead.organization_id == organization_id:
            return lead.title
    return None


def prepare_operation(
    db: Session,
    organization_id: uuid.UUID,
    intent: Intent,
    question: str,
    lead: Lead | None = None,
) -> tuple[ReadAnswer, ProposalDraft | None]:
    if lead is not None:
        leads = [lead]
    else:
        leads = leads_for_question(db, organization_id, question)
    if not leads and lead is None:
        name = requested_name(question)
        if name and _literal_name(name):
            leads = _matching_leads(db, organization_id, name)
    if len(leads) > 1:
        lines = [f"- {_clip(lead.title, 200)}" for lead in leads]
        return (
            _read(
                "More than one stored lead matches that name. "
                "Ask again with one of these titles.\n\n" + "\n".join(lines),
                [_lead_record(lead) for lead in leads],
            ),
            None,
        )
    if intent is Intent.summary and not leads:
        name = requested_name(question)
        contacts = _matching_contacts(db, organization_id, name) if name and _literal_name(name) else []
        if len(contacts) == 1:
            return _contact_summary(db, organization_id, contacts[0]), None
        if len(contacts) > 1:
            lines = [f"- {_clip(contact.full_name, 200)}" for contact in contacts]
            return _read("More than one contact matches that name.\n\n" + "\n".join(lines)), None
    if not leads:
        name = requested_name(question)
        if name and _literal_name(name):
            return _read(f'No lead in this organization matches "{name}".'), None
        return _read("Name the lead or customer so I can use the stored record."), None
    lead = leads[0]
    if intent is Intent.summary:
        return _lead_summary(db, organization_id, lead), None
    if intent is Intent.task:
        return _task_proposal(db, organization_id, lead)
    if intent is Intent.appointment:
        return _appointment_proposal(db, organization_id, lead)
    return _follow_up_proposal(db, organization_id, lead)


_CLAUSE = re.compile(
    r"[.?!]|,\s|\s+\b(?:about|including|before|then|and)\b",
    re.IGNORECASE,
)
_FACTISH = re.compile(
    r"\b(who|when|where|what|which|how|does|do|is|are|email|phone|status|count|"
    r"policy|document|note|notes)\b",
    re.IGNORECASE,
)
_STOP_NAMES = {
    "and",
    "are",
    "book",
    "but",
    "can",
    "contact",
    "customer",
    "email",
    "for",
    "from",
    "had",
    "has",
    "her",
    "his",
    "lead",
    "not",
    "note",
    "our",
    "send",
    "task",
    "that",
    "the",
    "them",
    "they",
    "this",
    "with",
    "you",
    "your",
}


def requested_name(question: str) -> str | None:
    text = " ".join(question.strip().split())
    match = _NAME.search(text) or _SUMMARY_NAME.search(text)
    if match is None:
        return None
    name = _LEADING_KIND.sub("", match.group(1).strip(" .?!"))
    name = _CLAUSE.split(name, maxsplit=1)[0]
    name = name.strip(" .?!,;:")
    if len(name) < 3:
        return None
    return name[:200]


def _literal_name(name: str) -> bool:
    return len(name) <= 80 and len(name.split()) <= 6 and "." not in name


def _folded(text: str) -> str:
    cleaned = text.casefold().replace("’", "'")
    cleaned = re.sub(r"'s\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return f" {cleaned.strip()} "


def _phrase(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.casefold()).split())


def contacts_named_in(db: Session, organization_id: uuid.UUID, text: str) -> list[Contact]:
    """Contacts in this organization whose stored name appears in the text."""

    folded = _folded(text)
    contacts = list(
        db.scalars(
            select(Contact)
            .where(Contact.organization_id == organization_id, Contact.archived_at.is_(None))
            .order_by(Contact.full_name.asc())
            .limit(300)
        ).all()
    )
    matched = [
        contact
        for contact in contacts
        if len(_phrase(contact.full_name)) >= 5 and f" {_phrase(contact.full_name)} " in folded
    ]
    if matched:
        return matched
    groups: dict[str, list[Contact]] = {}
    for contact in contacts:
        tokens = _phrase(contact.full_name).split()
        if not tokens:
            continue
        first = tokens[0]
        if len(first) < 3 or first in _STOP_NAMES:
            continue
        groups.setdefault(first, []).append(contact)
    return [
        group[0]
        for token, group in groups.items()
        if len(group) == 1 and f" {token} " in folded
    ]


def leads_for_question(db: Session, organization_id: uuid.UUID, question: str) -> list[Lead]:
    """Leads named in the question, or the lead linked to one named contact."""

    folded = _folded(question)
    leads = list(
        db.scalars(
            select(Lead)
            .where(Lead.organization_id == organization_id, Lead.archived_at.is_(None))
            .order_by(Lead.updated_at.desc())
            .limit(300)
        ).all()
    )
    titled = [
        lead
        for lead in leads
        if len(_phrase(lead.title)) >= 5 and f" {_phrase(lead.title)} " in folded
    ]
    if len(titled) == 1:
        return titled
    contacts = contacts_named_in(db, organization_id, question)
    if len(contacts) == 1:
        linked = [lead for lead in leads if lead.contact_id == contacts[0].id]
        if linked:
            return linked[:8]
    return titled[:8]


def needs_stored_excerpt(question: str) -> bool:
    """A second clause asks for a stored fact as well as the action."""

    text = " ".join(question.split())
    if len(text) < 40:
        return False
    return bool(re.search(r"[.?!]|\b(include|including|before|still|what|when)\b", text, re.I))


def relates_written_person(question: str) -> bool:
    text = question.casefold()
    written = re.search(r"\b(document|documents|note|notes|file|passage|policy|procedure)\b", text)
    person = re.search(r"\b(contact|contacts|crm|customer)\b", text)
    return bool(written and person)


def clarify_named_work(db: Session, organization_id: uuid.UUID, question: str) -> str | None:
    """Identify one named person when the request does not ask for a fact or an action."""

    from app.domains.assistant.routing import operation_intents

    if operation_intents(question) or _FACTISH.search(question) or relates_written_person(question):
        return None
    contacts = contacts_named_in(db, organization_id, question)
    if len(contacts) > 1:
        names = ", ".join(_clip(contact.full_name, 80) for contact in contacts[:4])
        return f"Which person do you mean: {names}?"
    if len(contacts) != 1:
        return None
    contact = contacts[0]
    leads = [
        lead
        for lead in leads_for_question(db, organization_id, question)
        if lead.contact_id == contact.id
    ]
    if len(leads) == 1:
        return (
            f"{_clip(contact.full_name, 200)} is a contact on {_clip(leads[0].title, 200)}. "
            "What should I do with that lead?"
        )
    return (
        f"{_clip(contact.full_name, 200)} is a contact in this workspace. "
        "What should I do for them?"
    )


def attach_proposal(
    db: Session, conversation: Conversation, message: Message, draft: ProposalDraft
) -> AssistantProposal:
    proposal = AssistantProposal(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        message_id=message.id,
        kind=draft.kind,
        status="proposed",
        title=draft.title[:200],
        summary=draft.summary,
        payload=draft.payload,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def proposals_for_messages(
    db: Session, organization_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ProposalOut]]:
    if not message_ids:
        return {}
    rows = list(
        db.scalars(
            select(AssistantProposal)
            .where(
                AssistantProposal.organization_id == organization_id,
                AssistantProposal.message_id.in_(message_ids),
            )
            .order_by(AssistantProposal.created_at.asc())
        ).all()
    )
    approval_ids = [row.approval_id for row in rows if row.approval_id is not None]
    statuses: dict[uuid.UUID, str] = {}
    if approval_ids:
        pairs = db.execute(
            select(Approval.id, Approval.status).where(
                Approval.organization_id == organization_id,
                Approval.id.in_(approval_ids),
            )
        ).all()
        statuses = {
            approval_id: status.value if hasattr(status, "value") else str(status)
            for approval_id, status in pairs
        }
    grouped: dict[uuid.UUID, list[ProposalOut]] = {}
    for row in rows:
        grouped.setdefault(row.message_id, []).append(_proposal_out(row, statuses.get(row.approval_id)))
    return grouped


def submit_proposal(
    db: Session,
    conversation: Conversation,
    proposal_id: uuid.UUID,
    user_id: uuid.UUID,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> ProposalOut:
    proposal = _owned_proposal(db, conversation, proposal_id)
    if proposal.status != "proposed":
        raise AppError(409, "proposal_closed", "This proposal is no longer open")
    if proposal.kind == "task":
        _create_task(db, conversation, proposal, user_id)
    elif proposal.kind == "appointment":
        _create_appointment(db, conversation, proposal, user_id, starts_at, ends_at)
    else:
        _create_follow_up(db, conversation, proposal, user_id)
    db.commit()
    db.refresh(proposal)
    return proposals_for_messages(db, conversation.organization_id, [proposal.message_id])[
        proposal.message_id
    ][-1]


def dismiss_proposal(
    db: Session, conversation: Conversation, proposal_id: uuid.UUID
) -> ProposalOut:
    proposal = _owned_proposal(db, conversation, proposal_id)
    if proposal.status != "proposed":
        raise AppError(409, "proposal_closed", "This proposal is no longer open")
    proposal.status = "dismissed"
    db.commit()
    db.refresh(proposal)
    return _proposal_out(proposal, None)


def _create_task(
    db: Session, conversation: Conversation, proposal: AssistantProposal, user_id: uuid.UUID
) -> None:
    lead = _lead_from_payload(db, conversation.organization_id, proposal.payload)
    contact_id = _optional_uuid(proposal.payload.get("contact_id"))
    if contact_id is not None and _contact(db, conversation.organization_id, contact_id) is None:
        raise AppError(404, "not_found", "Resource not found")
    title = str(proposal.payload.get("title") or proposal.title)[:200]
    description = proposal.payload.get("description")
    task = WorkflowTask(
        organization_id=conversation.organization_id,
        title=title,
        description=description if isinstance(description, str) else None,
        lead_id=lead.id,
        contact_id=contact_id,
        assignee_user_id=user_id,
        priority="normal",
        source="manual",
    )
    db.add(task)
    db.flush()
    proposal.status = "submitted"
    proposal.task_id = task.id


def _create_appointment(
    db: Session,
    conversation: Conversation,
    proposal: AssistantProposal,
    user_id: uuid.UUID,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> None:
    if starts_at is None or ends_at is None or starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise AppError(422, "appointment_time_required", "Choose a start and end time")
    if ends_at <= starts_at:
        raise AppError(422, "appointment_time_required", "The end time must be after the start")
    lead = _lead_from_payload(db, conversation.organization_id, proposal.payload)
    inquiry = _inquiry_from_payload(db, conversation.organization_id, proposal.payload, lead.id)
    body = str(proposal.payload.get("body") or f"Appointment requested: {inquiry.subject}")
    run = _open_run(db, conversation.organization_id, inquiry, user_id)
    approval = create_approval(
        db,
        organization_id=conversation.organization_id,
        run_id=run.id,
        requested_by=user_id,
        action_type=ActionType.request_appointment,
        payload={
            "lead_id": str(lead.id),
            "body": body[:4000],
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
        position=0,
        commit=False,
    )
    proposal.status = "submitted"
    proposal.run_id = run.id
    proposal.approval_id = approval.id


def _create_follow_up(
    db: Session, conversation: Conversation, proposal: AssistantProposal, user_id: uuid.UUID
) -> None:
    lead = _lead_from_payload(db, conversation.organization_id, proposal.payload)
    contact = _contact_from_payload(db, conversation.organization_id, proposal.payload)
    if lead.contact_id != contact.id:
        raise AppError(409, "recipient_not_owned", "The recipient is not linked to this lead")
    channel = str(proposal.payload.get("channel") or "")
    current = contact.email if channel == "email" else contact.phone
    snapshot = proposal.payload.get("recipient_snapshot")
    if not isinstance(current, str) or not isinstance(snapshot, str) or current != snapshot:
        raise AppError(
            409,
            "recipient_changed",
            "The stored recipient changed. Ask for a new draft.",
        )
    inquiry = _inquiry_from_payload(db, conversation.organization_id, proposal.payload, lead.id)
    payload = {
        "lead_id": str(lead.id),
        "contact_id": str(contact.id),
        "to": current,
        "recipient_snapshot": current,
        "subject": str(proposal.payload.get("subject") or lead.title)[:200],
        "body": str(proposal.payload.get("body") or "")[:4000],
        "channel": channel,
    }
    conversation_id = proposal.payload.get("conversation_id")
    if isinstance(conversation_id, str) and conversation_id:
        payload["conversation_id"] = conversation_id
    if not payload["body"].strip():
        raise AppError(409, "approval_invalid", "The draft has no message")
    run = _open_run(db, conversation.organization_id, inquiry, user_id)
    approval = create_approval(
        db,
        organization_id=conversation.organization_id,
        run_id=run.id,
        requested_by=user_id,
        action_type=ActionType.prepare_customer_response,
        payload=payload,
        position=0,
        commit=False,
    )
    proposal.status = "submitted"
    proposal.run_id = run.id
    proposal.approval_id = approval.id


def _lead_summary(db: Session, organization_id: uuid.UUID, lead: Lead) -> ReadAnswer:
    contact = _contact(db, organization_id, lead.contact_id) if lead.contact_id else None
    company = _company(db, organization_id, contact.company_id) if contact and contact.company_id else None
    inquiry = _latest_inquiry(db, organization_id, lead.id)
    messages = _inbox_messages(db, organization_id, contact.id) if contact else []
    lines = [
        f"## {_clip(lead.title, 200)}",
        "",
        "Stored records only. No detail was added beyond these fields.",
        "",
        f"- Lead status: {lead.status.value if hasattr(lead.status, 'value') else lead.status}",
        f"- Notes: {_clip(lead.notes, 400) if lead.notes else 'None stored'}",
    ]
    records = [_lead_record(lead)]
    if contact:
        address = contact.email or contact.phone or "No email or phone stored"
        lines.append(f"- Contact: {_clip(contact.full_name, 200)} ({address})")
        records.append(
            {
                "record_type": "contact",
                "record_id": str(contact.id),
                "title": _clip(contact.full_name, 200),
                "excerpt": address,
            }
        )
    else:
        lines.append("- Contact: None stored")
    if company:
        lines.append(f"- Company: {_clip(company.name, 200)}")
        records.append(
            {
                "record_type": "company",
                "record_id": str(company.id),
                "title": _clip(company.name, 200),
                "excerpt": company.industry or company.name,
            }
        )
    if inquiry:
        lines.append(f"- Inquiry: {_clip(inquiry.subject, 200)}")
        lines.append(f"- Inquiry message: {_clip(inquiry.body, 400)}")
        records.append(
            {
                "record_type": "inquiry",
                "record_id": str(inquiry.id),
                "title": _clip(inquiry.subject, 200),
                "excerpt": _clip(inquiry.body, 400),
            }
        )
    else:
        lines.append("- Inquiry: None stored")
    if messages:
        lines.append("- Latest customer conversation:")
        for item, thread in messages:
            lines.append(f"  - {item.direction}: {_clip(item.body, 240)}")
            records.append(
                {
                    "record_type": "conversation",
                    "record_id": str(thread.id),
                    "title": _clip(thread.subject, 200),
                    "excerpt": _clip(item.body, 400),
                }
            )
    else:
        lines.append("- Inbox: No conversation is linked to this contact")
    return _read("\n".join(lines), records)


def _contact_summary(db: Session, organization_id: uuid.UUID, contact: Contact) -> ReadAnswer:
    company = _company(db, organization_id, contact.company_id) if contact.company_id else None
    lines = [
        f"## {_clip(contact.full_name, 200)}",
        "",
        "Stored contact only. No lead is linked, so this is not a lead summary.",
        "",
        f"- Email: {contact.email or 'None stored'}",
        f"- Phone: {contact.phone or 'None stored'}",
    ]
    records = [
        {
            "record_type": "contact",
            "record_id": str(contact.id),
            "title": _clip(contact.full_name, 200),
            "excerpt": contact.email or contact.phone or contact.full_name,
        }
    ]
    if company:
        lines.append(f"- Company: {_clip(company.name, 200)}")
    return _read("\n".join(lines), records)


def _task_proposal(
    db: Session, organization_id: uuid.UUID, lead: Lead
) -> tuple[ReadAnswer, ProposalDraft]:
    inquiry = _latest_inquiry(db, organization_id, lead.id)
    description = _clip(inquiry.body, 400) if inquiry else "No inquiry is stored for this lead."
    title = f"Follow up: {_clip(lead.title, 180)}"
    summary = (
        f"Proposed task for {_clip(lead.title, 200)}. "
        "Confirming creates the task in this workspace. It does not send a message."
    )
    draft = ProposalDraft(
        kind="task",
        title=title,
        summary=summary,
        payload={
            "lead_id": str(lead.id),
            "contact_id": str(lead.contact_id) if lead.contact_id else None,
            "title": title,
            "description": description,
        },
    )
    return _read(summary + f"\n\n- Title: {title}\n- Detail: {description}", [_lead_record(lead)]), draft


def _customer_context(
    db: Session, organization_id: uuid.UUID, lead: Lead
) -> tuple[Contact | None, Company | None]:
    contact = _contact(db, organization_id, lead.contact_id) if lead.contact_id else None
    company = _company(db, organization_id, contact.company_id) if contact and contact.company_id else None
    return contact, company


def _appointment_proposal(
    db: Session, organization_id: uuid.UUID, lead: Lead
) -> tuple[ReadAnswer, ProposalDraft | None]:
    inquiry = _latest_inquiry(db, organization_id, lead.id)
    if inquiry is None:
        return _read("This lead has no inquiry, so an appointment approval cannot be requested."), None
    contact, company = _customer_context(db, organization_id, lead)
    who = _clip(contact.full_name, 200) if contact else "the stored lead"
    where = f" at {_clip(company.name, 200)}" if company else ""
    body = f"Appointment requested: {_clip(inquiry.subject, 200)}"
    summary = (
        f"Proposed appointment for {_clip(lead.title, 200)}{where} with {who}. "
        f"The inquiry is {_clip(inquiry.subject, 200)}. "
        "Choose a time and request approval. Nothing is booked until an administrator approves it."
    )
    draft = ProposalDraft(
        kind="appointment",
        title=f"Appointment: {_clip(lead.title, 180)}",
        summary=summary,
        payload={"lead_id": str(lead.id), "inquiry_id": str(inquiry.id), "body": body},
    )
    records = [_lead_record(lead)]
    if contact is not None:
        records.append(
            {
                "record_type": "contact",
                "record_id": str(contact.id),
                "title": _clip(contact.full_name, 200),
                "excerpt": contact.email or contact.full_name,
            }
        )
    if company is not None:
        records.append(
            {
                "record_type": "company",
                "record_id": str(company.id),
                "title": _clip(company.name, 200),
                "excerpt": company.industry or company.name,
            }
        )
    return _read(summary + f"\n\n- Request: {body}", records), draft


def _follow_up_proposal(
    db: Session, organization_id: uuid.UUID, lead: Lead
) -> tuple[ReadAnswer, ProposalDraft | None]:
    inquiry = _latest_inquiry(db, organization_id, lead.id)
    if inquiry is None:
        return _read("This lead has no inquiry, so a follow-up approval cannot be requested."), None
    contact = _contact(db, organization_id, lead.contact_id) if lead.contact_id else None
    if contact is None:
        return _read("This lead has no contact, so there is no recipient for a follow-up."), None
    channel, address, thread_id = _reply_channel(db, organization_id, contact)
    if channel is None or address is None:
        return (
            _read(
                "This contact has no email, and no WhatsApp conversation from the customer "
                "to use for a follow-up."
            ),
            None,
        )
    source = _latest_customer_text(db, organization_id, contact.id) or inquiry.body
    company = _company(db, organization_id, contact.company_id) if contact.company_id else None
    where = f" at {_clip(company.name, 120)}" if company else ""
    body = (
        f"Hello {_clip(contact.full_name, 120)}, this follows up on "
        f"{_clip(lead.title, 160)}{where}. "
        f'You wrote: "{_clip(source, 320)}". Reply with how you would like to proceed.'
    )
    summary = (
        f"Proposed follow-up for {_clip(lead.title, 200)}. "
        "Requesting approval does not send it."
    )
    payload: dict[str, Any] = {
        "lead_id": str(lead.id),
        "contact_id": str(contact.id),
        "inquiry_id": str(inquiry.id),
        "channel": channel,
        "to": address,
        "recipient_snapshot": address,
        "subject": _clip(lead.title, 200),
        "body": body,
    }
    if thread_id is not None:
        payload["conversation_id"] = str(thread_id)
    draft = ProposalDraft(
        kind="follow_up",
        title=f"Follow-up: {_clip(lead.title, 180)}",
        summary=summary,
        payload=payload,
    )
    content = "\n".join(
        [
            summary,
            "",
            f"- Channel: {channel}",
            f"- Recipient: {address}",
            f"- Subject: {_clip(lead.title, 200)}",
            f"- Draft: {body}",
        ]
    )
    return _read(content, [_lead_record(lead)]), draft


def _reply_channel(
    db: Session, organization_id: uuid.UUID, contact: Contact
) -> tuple[str | None, str | None, uuid.UUID | None]:
    if contact.email:
        return "email", contact.email, None
    if not contact.phone:
        return None, None, None
    thread = db.scalar(
        select(InboxConversation)
        .join(InboxMessage, InboxMessage.conversation_id == InboxConversation.id)
        .where(
            InboxConversation.organization_id == organization_id,
            InboxConversation.contact_id == contact.id,
            InboxConversation.channel == "whatsapp",
            InboxMessage.organization_id == organization_id,
            InboxMessage.direction == "inbound",
        )
        .order_by(InboxMessage.created_at.desc())
        .limit(1)
    )
    if thread is None:
        return None, None, None
    return "whatsapp", contact.phone, thread.id


def _latest_customer_text(db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID) -> str | None:
    message = db.scalar(
        select(InboxMessage)
        .join(InboxConversation, InboxConversation.id == InboxMessage.conversation_id)
        .where(
            InboxMessage.organization_id == organization_id,
            InboxConversation.organization_id == organization_id,
            InboxConversation.contact_id == contact_id,
            InboxMessage.direction == "inbound",
        )
        .order_by(InboxMessage.created_at.desc())
        .limit(1)
    )
    return message.body if message else None


def _inbox_messages(
    db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> list[tuple[InboxMessage, InboxConversation]]:
    rows = db.execute(
        select(InboxMessage, InboxConversation)
        .join(InboxConversation, InboxConversation.id == InboxMessage.conversation_id)
        .where(
            InboxMessage.organization_id == organization_id,
            InboxConversation.organization_id == organization_id,
            InboxConversation.contact_id == contact_id,
        )
        .order_by(InboxMessage.created_at.desc())
        .limit(3)
    ).all()
    return [(message, thread) for message, thread in rows]


def _priority_lead_title(db: Session, organization_id: uuid.UUID) -> str | None:
    for status in (LeadStatus.new, LeadStatus.contacted, LeadStatus.qualified):
        rows, _total = crm.list_leads(
            db,
            organization_id,
            q=None,
            status=status.value,
            company_id=None,
            owner_user_id=None,
            origin=None,
            page=1,
            page_size=8,
        )
        for lead in rows:
            if _latest_inquiry(db, organization_id, lead.id) is not None:
                return lead.title
    return None


def _matching_leads(db: Session, organization_id: uuid.UUID, name: str) -> list[Lead]:
    pattern = _like(name)
    return list(
        db.scalars(
            select(Lead)
            .outerjoin(Contact, Contact.id == Lead.contact_id)
            .where(
                Lead.organization_id == organization_id,
                Lead.archived_at.is_(None),
                or_(Lead.title.ilike(pattern, escape="\\"), Contact.full_name.ilike(pattern, escape="\\")),
            )
            .order_by(Lead.updated_at.desc())
            .limit(8)
        ).unique()
    )


def _matching_contacts(db: Session, organization_id: uuid.UUID, name: str) -> list[Contact]:
    pattern = _like(name)
    return list(
        db.scalars(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.archived_at.is_(None),
                Contact.full_name.ilike(pattern, escape="\\"),
            )
            .order_by(Contact.full_name.asc())
            .limit(8)
        ).all()
    )


def _owned_proposal(
    db: Session, conversation: Conversation, proposal_id: uuid.UUID
) -> AssistantProposal:
    proposal = db.scalar(
        select(AssistantProposal).where(
            AssistantProposal.id == proposal_id,
            AssistantProposal.organization_id == conversation.organization_id,
            AssistantProposal.conversation_id == conversation.id,
        )
    )
    if proposal is None:
        raise AppError(404, "not_found", "Resource not found")
    return proposal


def _open_run(
    db: Session, organization_id: uuid.UUID, inquiry: Inquiry, user_id: uuid.UUID
) -> AgentRun:
    run = AgentRun(
        organization_id=organization_id,
        inquiry_id=inquiry.id,
        started_by=user_id,
        status=RunStatus.awaiting_approval,
        origin=inquiry.origin,
    )
    db.add(run)
    db.flush()
    return run


def _lead_from_payload(db: Session, organization_id: uuid.UUID, payload: dict[str, Any]) -> Lead:
    lead = db.scalar(
        select(Lead).where(
            Lead.id == _required_uuid(payload.get("lead_id")),
            Lead.organization_id == organization_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        raise AppError(404, "not_found", "Resource not found")
    return lead


def _contact_from_payload(
    db: Session, organization_id: uuid.UUID, payload: dict[str, Any]
) -> Contact:
    contact = _contact(db, organization_id, _required_uuid(payload.get("contact_id")))
    if contact is None:
        raise AppError(404, "not_found", "Resource not found")
    return contact


def _inquiry_from_payload(
    db: Session, organization_id: uuid.UUID, payload: dict[str, Any], lead_id: uuid.UUID
) -> Inquiry:
    inquiry = db.scalar(
        select(Inquiry).where(
            Inquiry.id == _required_uuid(payload.get("inquiry_id")),
            Inquiry.organization_id == organization_id,
            Inquiry.lead_id == lead_id,
            Inquiry.archived_at.is_(None),
        )
    )
    if inquiry is None:
        raise AppError(404, "not_found", "Resource not found")
    return inquiry


def _contact(db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID | None) -> Contact | None:
    if contact_id is None:
        return None
    return db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == organization_id,
            Contact.archived_at.is_(None),
        )
    )


def _company(db: Session, organization_id: uuid.UUID, company_id: uuid.UUID | None) -> Company | None:
    if company_id is None:
        return None
    return db.scalar(
        select(Company).where(Company.id == company_id, Company.organization_id == organization_id)
    )


def _latest_inquiry(db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Inquiry | None:
    return db.scalar(
        select(Inquiry)
        .where(
            Inquiry.organization_id == organization_id,
            Inquiry.lead_id == lead_id,
            Inquiry.archived_at.is_(None),
        )
        .order_by(Inquiry.created_at.desc())
        .limit(1)
    )


def _proposal_out(row: AssistantProposal, approval_status: str | None) -> ProposalOut:
    payload = row.payload if isinstance(row.payload, dict) else {}
    return ProposalOut(
        id=row.id,
        kind=row.kind,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        title=row.title,
        summary=row.summary,
        result_label=_result_label(row, approval_status),
        lead_id=_optional_uuid(payload.get("lead_id")),
        contact_id=_optional_uuid(payload.get("contact_id")),
        inquiry_id=_optional_uuid(payload.get("inquiry_id")),
        approval_id=row.approval_id,
        approval_status=approval_status,
        task_id=row.task_id,
        run_id=row.run_id,
    )


def _result_label(row: AssistantProposal, approval_status: str | None) -> str:
    if row.status == "dismissed":
        return "Dismissed. Nothing was changed."
    if row.status == "proposed":
        return "Proposed. Nothing has been sent, booked, or created."
    if row.kind == "task" and row.task_id is not None:
        return "Task created in this workspace. No message was sent."
    if approval_status == "executed":
        return "Approved and completed."
    if approval_status == "rejected":
        return "Rejected. Nothing was sent or booked."
    if approval_status in {"failed", "needs_attention"}:
        return "The action did not complete. Nothing new was recorded as sent."
    if approval_status == "pending":
        return "Waiting for approval. Nothing has been sent or booked."
    return "Submitted. Open the linked record for the result."


def _lead_record(lead: Lead) -> dict[str, str]:
    status = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
    return {
        "record_type": "lead",
        "record_id": str(lead.id),
        "title": _clip(lead.title, 200),
        "excerpt": f"Status: {status}",
    }


def _read(content: str, records: list[dict[str, str]] | None = None) -> ReadAnswer:
    return ReadAnswer(
        content=content,
        crm_records=records or [],
        documents=[],
        searched_crm=True,
        searched_documents=False,
    )


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _clip(value: str | None, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _required_uuid(value: object) -> uuid.UUID:
    parsed = _optional_uuid(value)
    if parsed is None:
        raise AppError(409, "approval_invalid", "The proposal is missing a stored record")
    return parsed


def _optional_uuid(value: object) -> uuid.UUID | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppError(409, "approval_invalid", "The proposal has an invalid record") from exc
