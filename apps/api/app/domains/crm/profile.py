"""A customer profile assembled from records the organization already stored."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.automation.models import CalendarBooking, WorkflowTask
from app.domains.crm.models import Company, Contact, Inquiry, Interaction, Lead, Opportunity
from app.domains.identity.models import User
from app.domains.inbox.models import InboxConversation

_LIMIT = 25


def customer_profile(
    db: Session,
    organization_id: uuid.UUID,
    *,
    company_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
    lead_id: uuid.UUID | None,
) -> dict[str, Any]:
    chosen = [item for item in (company_id, contact_id, lead_id) if item is not None]
    if len(chosen) != 1:
        raise AppError(422, "profile_target_required", "Choose one company, contact, or lead.")
    company_ids: set[uuid.UUID] = set()
    contact_ids: set[uuid.UUID] = set()
    lead_ids: set[uuid.UUID] = set()
    if company_id is not None:
        company = _load(db, Company, organization_id, company_id)
        subject = _subject("company", company.id, company.name, company.archived_at)
        company_ids.add(company.id)
    elif contact_id is not None:
        contact = _load(db, Contact, organization_id, contact_id)
        subject = _subject("contact", contact.id, contact.full_name, contact.archived_at)
        contact_ids.add(contact.id)
        if contact.company_id is not None:
            company_ids.add(contact.company_id)
    else:
        assert lead_id is not None
        lead = _load(db, Lead, organization_id, lead_id)
        subject = _subject("lead", lead.id, lead.title, lead.archived_at)
        lead_ids.add(lead.id)
        if lead.company_id is not None:
            company_ids.add(lead.company_id)
        if lead.contact_id is not None:
            contact_ids.add(lead.contact_id)

    contacts = _related_contacts(db, organization_id, company_ids, contact_ids)
    contact_ids.update(item.id for item in contacts)
    leads = _related_leads(db, organization_id, company_ids, contact_ids, lead_ids)
    lead_ids.update(item.id for item in leads)
    inquiries = _related_inquiries(db, organization_id, company_ids, lead_ids)
    opportunities = _related_opportunities(
        db, organization_id, company_ids, contact_ids, lead_ids
    )
    opportunity_ids = {item.id for item in opportunities}
    conversations = _conversations(db, organization_id, contact_ids, lead_ids)
    appointments = _appointments(db, organization_id, lead_ids)
    tasks = _tasks(db, organization_id, contact_ids, lead_ids, opportunity_ids)
    interactions = _interactions(db, organization_id, lead_ids)
    return {
        "subject": subject,
        "companies": [_company_row(db, organization_id, item) for item in company_ids],
        "contacts": [_brief(item.id, item.full_name, item.email) for item in contacts],
        "leads": [_brief(item.id, item.title, item.status.value) for item in leads],
        "inquiries": [_brief(item.id, item.subject, None) for item in inquiries],
        "opportunities": [
            {"id": item.id, "title": item.title, "stage": item.stage, "value": item.value}
            for item in opportunities
        ],
        "conversations": [
            {
                "id": item.id,
                "subject": item.subject,
                "channel": item.channel.value,
                "status": item.status.value,
                "updated_at": item.updated_at,
            }
            for item in conversations
        ],
        "appointments": [
            {
                "id": item.id,
                "lead_id": item.lead_id,
                "status": item.status.value,
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
            }
            for item in appointments
        ],
        "tasks": tasks,
        "activity": _activity(inquiries, interactions, appointments, tasks, conversations),
    }


def _subject(
    kind: str, record_id: uuid.UUID, title: str, archived_at: datetime | None
) -> dict[str, Any]:
    return {"kind": kind, "id": record_id, "title": title, "archived": archived_at is not None}


def _brief(record_id: uuid.UUID, title: str, detail: str | None) -> dict[str, Any]:
    return {"id": record_id, "title": title, "detail": detail}


def _load(db: Session, model: Any, organization_id: uuid.UUID, record_id: uuid.UUID) -> Any:
    row = db.scalar(
        select(model).where(model.id == record_id, model.organization_id == organization_id)
    )
    if row is None:
        raise AppError(404, "not_found", "Resource not found")
    return row


def _company_row(db: Session, organization_id: uuid.UUID, company_id: uuid.UUID) -> dict[str, Any]:
    company = db.scalar(
        select(Company).where(Company.id == company_id, Company.organization_id == organization_id)
    )
    if company is None:
        return {"id": company_id, "title": "Company", "detail": None}
    return {"id": company.id, "title": company.name, "detail": company.industry}


def _related_contacts(
    db: Session,
    organization_id: uuid.UUID,
    company_ids: set[uuid.UUID],
    contact_ids: set[uuid.UUID],
) -> list[Contact]:
    clauses = []
    if company_ids:
        clauses.append(Contact.company_id.in_(company_ids))
    if contact_ids:
        clauses.append(Contact.id.in_(contact_ids))
    if not clauses:
        return []
    return list(
        db.scalars(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.archived_at.is_(None),
                or_(*clauses),
            )
            .order_by(Contact.full_name.asc())
            .limit(_LIMIT)
        ).all()
    )


def _related_leads(
    db: Session,
    organization_id: uuid.UUID,
    company_ids: set[uuid.UUID],
    contact_ids: set[uuid.UUID],
    lead_ids: set[uuid.UUID],
) -> list[Lead]:
    clauses = []
    if company_ids:
        clauses.append(Lead.company_id.in_(company_ids))
    if contact_ids:
        clauses.append(Lead.contact_id.in_(contact_ids))
    if lead_ids:
        clauses.append(Lead.id.in_(lead_ids))
    if not clauses:
        return []
    return list(
        db.scalars(
            select(Lead)
            .where(
                Lead.organization_id == organization_id, Lead.archived_at.is_(None), or_(*clauses)
            )
            .order_by(Lead.updated_at.desc())
            .limit(_LIMIT)
        ).all()
    )


def _related_inquiries(
    db: Session, organization_id: uuid.UUID, company_ids: set[uuid.UUID], lead_ids: set[uuid.UUID]
) -> list[Inquiry]:
    clauses = []
    if company_ids:
        clauses.append(Inquiry.company_id.in_(company_ids))
    if lead_ids:
        clauses.append(Inquiry.lead_id.in_(lead_ids))
    if not clauses:
        return []
    return list(
        db.scalars(
            select(Inquiry)
            .where(
                Inquiry.organization_id == organization_id,
                Inquiry.archived_at.is_(None),
                or_(*clauses),
            )
            .order_by(Inquiry.created_at.desc())
            .limit(_LIMIT)
        ).all()
    )


def _related_opportunities(
    db: Session,
    organization_id: uuid.UUID,
    company_ids: set[uuid.UUID],
    contact_ids: set[uuid.UUID],
    lead_ids: set[uuid.UUID],
) -> list[Opportunity]:
    clauses = []
    if company_ids:
        clauses.append(Opportunity.company_id.in_(company_ids))
    if contact_ids:
        clauses.append(Opportunity.contact_id.in_(contact_ids))
    if lead_ids:
        clauses.append(Opportunity.lead_id.in_(lead_ids))
    if not clauses:
        return []
    return list(
        db.scalars(
            select(Opportunity)
            .where(
                Opportunity.organization_id == organization_id,
                Opportunity.archived_at.is_(None),
                or_(*clauses),
            )
            .order_by(Opportunity.updated_at.desc())
            .limit(_LIMIT)
        ).all()
    )


def _conversations(
    db: Session,
    organization_id: uuid.UUID,
    contact_ids: set[uuid.UUID],
    lead_ids: set[uuid.UUID],
) -> list[InboxConversation]:
    clauses = []
    if contact_ids:
        clauses.append(InboxConversation.contact_id.in_(contact_ids))
    if lead_ids:
        clauses.append(InboxConversation.lead_id.in_(lead_ids))
    if not clauses:
        return []
    return list(
        db.scalars(
            select(InboxConversation)
            .where(InboxConversation.organization_id == organization_id, or_(*clauses))
            .order_by(InboxConversation.updated_at.desc())
            .limit(_LIMIT)
        ).all()
    )


def _appointments(
    db: Session, organization_id: uuid.UUID, lead_ids: set[uuid.UUID]
) -> list[CalendarBooking]:
    if not lead_ids:
        return []
    return list(
        db.scalars(
            select(CalendarBooking)
            .where(
                CalendarBooking.organization_id == organization_id,
                CalendarBooking.lead_id.in_(lead_ids),
            )
            .order_by(CalendarBooking.starts_at.desc())
            .limit(_LIMIT)
        ).all()
    )


def _tasks(
    db: Session,
    organization_id: uuid.UUID,
    contact_ids: set[uuid.UUID],
    lead_ids: set[uuid.UUID],
    opportunity_ids: set[uuid.UUID],
) -> list[dict[str, Any]]:
    clauses = []
    if contact_ids:
        clauses.append(WorkflowTask.contact_id.in_(contact_ids))
    if lead_ids:
        clauses.append(WorkflowTask.lead_id.in_(lead_ids))
    if opportunity_ids:
        clauses.append(WorkflowTask.opportunity_id.in_(opportunity_ids))
    if not clauses:
        return []
    rows = db.execute(
        select(WorkflowTask, User.full_name)
        .outerjoin(User, User.id == WorkflowTask.assignee_user_id)
        .where(WorkflowTask.organization_id == organization_id, or_(*clauses))
        .order_by(WorkflowTask.created_at.desc())
        .limit(_LIMIT)
    ).all()
    return [
        {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "priority": task.priority,
            "due_at": task.due_at,
            "created_at": task.created_at,
            "assignee": name,
            "lead_id": task.lead_id,
            "contact_id": task.contact_id,
        }
        for task, name in rows
    ]


def _interactions(
    db: Session, organization_id: uuid.UUID, lead_ids: set[uuid.UUID]
) -> list[Interaction]:
    if not lead_ids:
        return []
    return list(
        db.scalars(
            select(Interaction)
            .where(
                Interaction.organization_id == organization_id,
                Interaction.lead_id.in_(lead_ids),
            )
            .order_by(Interaction.created_at.desc())
            .limit(_LIMIT)
        ).all()
    )


def _activity(
    inquiries: list[Inquiry],
    interactions: list[Interaction],
    appointments: list[CalendarBooking],
    tasks: list[dict[str, Any]],
    conversations: list[InboxConversation],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for inquiry in inquiries:
        items.append(
            _event(
                inquiry.created_at,
                "request",
                inquiry.subject,
                _clip(inquiry.body),
                "inquiry",
                inquiry.id,
            )
        )
    for interaction in interactions:
        items.append(
            _event(
                interaction.created_at,
                interaction.kind.value,
                interaction.kind.value.replace("_", " ").title(),
                _clip(interaction.body),
                "lead",
                interaction.lead_id,
            )
        )
    for booking in appointments:
        items.append(
            _event(
                booking.starts_at,
                "appointment",
                "Appointment",
                booking.status.value.replace("_", " "),
                "lead",
                booking.lead_id,
            )
        )
    for task in tasks:
        when = task["due_at"] or task["created_at"]
        items.append(
            _event(
                when,
                "task",
                task["title"],
                f"{task['status'].replace('_', ' ')} · {task['priority']}",
                "task",
                task["id"],
            )
        )
    for conversation in conversations:
        channel = conversation.channel.replace("_", " ")
        items.append(
            _event(
                conversation.updated_at,
                "conversation",
                conversation.subject or channel.title(),
                conversation.status.value.replace("_", " "),
                "conversation",
                conversation.id,
            )
        )
    items.sort(key=lambda item: item["at"], reverse=True)
    return items[:40]


def _event(
    when: datetime, kind: str, title: str, detail: str, record_kind: str, record_id: uuid.UUID
) -> dict[str, Any]:
    return {
        "at": when,
        "kind": kind,
        "title": title,
        "detail": detail,
        "record_kind": record_kind,
        "record_id": record_id,
    }


def _clip(value: str | None) -> str:
    text = (value or "").strip()
    if len(text) <= 180:
        return text
    return text[:177] + "..."
