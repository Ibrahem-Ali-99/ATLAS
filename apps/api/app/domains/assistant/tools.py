"""Tenant-scoped Assistant tools. Arguments cannot choose another organization."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.analytics.service import snapshot
from app.domains.assistant.operations import ProposalDraft
from app.domains.assistant.routing import Intent
from app.domains.automation.models import WorkflowRun, WorkflowTask
from app.domains.crm import service as crm
from app.domains.crm.models import Contact, LeadStatus, Opportunity
from app.domains.identity.models import MembershipRole
from app.domains.identity.service import list_team
from app.domains.inbox.models import InboxConversation
from app.domains.knowledge.retrieval import PRODUCTION_PIPELINE, RetrievedChunk, search_chunks
from app.domains.provenance.origin import DataScope
from app.integrations.calendar import calendar_adapter
from app.integrations.language import EmbeddingClient

_PROVIDER_CODES = {
    "embedding_unconfigured",
    "embedding_unauthorized",
    "embedding_unavailable",
    "embedding_timeout",
    "embedding_rate_limited",
    "embedding_failed",
    "embedding_dimension_mismatch",
}
_ATTENTION = (LeadStatus.new, LeadStatus.contacted, LeadStatus.qualified)
_LIMIT = 8


class QueryArgs(BaseModel):
    query: str = Field(default="", max_length=200)
    limit: int | None = Field(default=None, ge=1, le=8)


class LeadArgs(BaseModel):
    query: str = Field(default="", max_length=200)
    needs_attention: bool = False
    limit: int | None = Field(default=None, ge=1, le=8)


class InboxArgs(BaseModel):
    query: str = Field(default="", max_length=200)
    limit: int | None = Field(default=None, ge=1, le=8)


class TaskArgs(BaseModel):
    query: str = Field(default="", max_length=200)
    overdue_only: bool = False
    limit: int | None = Field(default=None, ge=1, le=8)


class KnowledgeArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class WorkflowArgs(BaseModel):
    failed_only: bool = False
    limit: int | None = Field(default=None, ge=1, le=8)


class AvailabilityArgs(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class NamedArgs(BaseModel):
    lead_name: str = Field(default="", max_length=200)


@dataclass
class ToolContext:
    db: Session
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    embedder: EmbeddingClient
    conversation_id: uuid.UUID | None = None


@dataclass
class ToolOutcome:
    name: str
    arguments: dict[str, Any]
    status: str
    duration_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, str]] = field(default_factory=list)
    documents: list[RetrievedChunk] = field(default_factory=list)
    error_message: str | None = None
    recovery: str | None = None
    proposal: ProposalDraft | None = None
    document_search: str | None = None


def tool_schemas() -> list[dict[str, Any]]:
    return [_schema(name, description, model) for name, description, model, _runner in _TOOLS]


def execute_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> ToolOutcome:
    spec = next((item for item in _TOOLS if item[0] == name), None)
    started = time.perf_counter()
    if spec is None:
        return _failed(name, arguments, started, "That action is not available.", None)
    _name, _description, model, runner = spec
    try:
        parsed = model.model_validate(arguments)
    except ValidationError:
        return _failed(
            name,
            arguments,
            started,
            "The arguments were not valid.",
            "Ask for the missing detail, such as a name or a time range.",
        )
    try:
        outcome = runner(ctx, parsed)
    except AppError as exc:
        if exc.code in _PROVIDER_CODES:
            raise
        return _failed(name, parsed.model_dump(mode="json"), started, exc.message, None)
    except Exception:
        return _failed(name, parsed.model_dump(mode="json"), started, "The lookup failed.", None)
    outcome.duration_ms = _elapsed(started)
    outcome.arguments = parsed.model_dump(mode="json")
    return outcome


def _schema(name: str, description: str, model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            },
        },
    }


def _cap(limit: int | None) -> int:
    if not isinstance(limit, int):
        return _LIMIT
    return min(_LIMIT, max(1, limit))


def _list_companies(ctx: ToolContext, args: QueryArgs) -> ToolOutcome:
    size = _cap(args.limit)
    rows, total = crm.list_companies(
        ctx.db,
        ctx.organization_id,
        q=args.query or None,
        page=1,
        page_size=size,
    )
    payload_rows = [
        {"name": row.name, "industry": row.industry, "website": row.website} for row in rows
    ]
    records = [
        _crm("company", row.id, row.name, row.industry or row.website or row.name) for row in rows
    ]
    payload: dict[str, Any] = {"companies": payload_rows, "total": total}
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_companies", payload, records)


def _list_contacts(ctx: ToolContext, args: QueryArgs) -> ToolOutcome:
    size = _cap(args.limit)
    rows, total = crm.list_contacts(
        ctx.db,
        ctx.organization_id,
        q=args.query or None,
        company_id=None,
        page=1,
        page_size=size,
    )
    payload_rows = [
        {"name": row.full_name, "email": row.email, "title": row.title} for row in rows
    ]
    records = [
        _crm("contact", row.id, row.full_name, row.email or row.title or row.full_name)
        for row in rows
    ]
    payload: dict[str, Any] = {"contacts": payload_rows, "total": total}
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_contacts", payload, records)


def _list_leads(ctx: ToolContext, args: LeadArgs) -> ToolOutcome:
    size = _cap(args.limit)
    term = args.query.strip() or None
    if args.needs_attention:
        rows = []
        total = 0
        for status in _ATTENTION:
            found, count = crm.list_leads(
                ctx.db,
                ctx.organization_id,
                q=term,
                status=status.value,
                company_id=None,
                owner_user_id=None,
                origin=None,
                page=1,
                page_size=size,
            )
            total += count
            for row in found:
                if len(rows) < size:
                    rows.append(row)
    else:
        rows, total = crm.list_leads(
            ctx.db,
            ctx.organization_id,
            q=term,
            status=None,
            company_id=None,
            owner_user_id=None,
            origin=None,
            page=1,
            page_size=size,
        )
    contact_ids = [row.contact_id for row in rows[:size] if row.contact_id]
    contact_names = {}
    if contact_ids:
        contact_names = {
            contact_id: full_name
            for contact_id, full_name in ctx.db.execute(
                select(Contact.id, Contact.full_name).where(
                    Contact.organization_id == ctx.organization_id,
                    Contact.id.in_(contact_ids),
                )
            ).all()
        }
    payload_rows = [
        {
            "title": row.title,
            "status": _enum(row.status),
            "notes": _clip(row.notes),
            "contact": contact_names.get(row.contact_id),
        }
        for row in rows[:size]
    ]
    records = [
        _crm("lead", row.id, row.title, f"{_enum(row.status)}. {_clip(row.notes) or row.title}")
        for row in rows[:size]
    ]
    payload: dict[str, Any] = {
        "leads": payload_rows,
        "total": total,
        "needs_attention": args.needs_attention,
    }
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_leads", payload, records)


def _list_members(ctx: ToolContext, args: QueryArgs) -> ToolOutcome:
    size = _cap(args.limit)
    include_email = ctx.role == MembershipRole.admin
    payload_rows = []
    records = []
    for membership, user in list_team(ctx.db, ctx.organization_id):
        role = _enum(membership.role)
        item: dict[str, Any] = {"name": user.full_name, "role": role}
        if include_email:
            item["email"] = user.email
        payload_rows.append(item)
        records.append(_crm("member", user.id, user.full_name, role))
    payload: dict[str, Any] = {"members": payload_rows[:size], "total": len(payload_rows)}
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_members", payload, records[:size])


def _list_opportunities(ctx: ToolContext, args: QueryArgs) -> ToolOutcome:
    size = _cap(args.limit)
    query = select(Opportunity).where(
        Opportunity.organization_id == ctx.organization_id,
        Opportunity.archived_at.is_(None),
    )
    if args.query:
        query = query.where(Opportunity.title.ilike(f"%{args.query}%"))
    rows = list(ctx.db.scalars(query.order_by(Opportunity.updated_at.desc()).limit(size)).all())
    payload_rows = [
        {
            "title": row.title,
            "stage": row.stage,
            "value": row.value,
            "currency": row.currency,
        }
        for row in rows
    ]
    records = [
        _crm("opportunity", row.id, row.title, f"{row.stage}. {row.value or ''} {row.currency}")
        for row in rows
    ]
    payload: dict[str, Any] = {"opportunities": payload_rows, "total": len(rows)}
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_opportunities", payload, records)


def _list_tasks(ctx: ToolContext, args: TaskArgs) -> ToolOutcome:
    from datetime import UTC, datetime

    size = _cap(args.limit)
    now = datetime.now(UTC)
    query = select(WorkflowTask).where(
        WorkflowTask.organization_id == ctx.organization_id,
        WorkflowTask.status == "open",
    )
    if args.overdue_only:
        query = query.where(WorkflowTask.due_at.is_not(None), WorkflowTask.due_at < now)
    rows = list(
        ctx.db.scalars(query.order_by(WorkflowTask.due_at.asc().nulls_last()).limit(size)).all()
    )
    payload_rows = [
        {
            "title": row.title,
            "status": row.status,
            "due_at": None if row.due_at is None else row.due_at.isoformat(),
            "priority": row.priority,
            "overdue": row.due_at is not None and row.due_at < now,
        }
        for row in rows
    ]
    records = [
        _crm("task", row.id, row.title, row.due_at.isoformat() if row.due_at else row.status)
        for row in rows
    ]
    payload: dict[str, Any] = {
        "tasks": payload_rows,
        "total": len(rows),
        "overdue_only": args.overdue_only,
    }
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_tasks", payload, records)


def _search_inbox(ctx: ToolContext, args: InboxArgs) -> ToolOutcome:
    size = _cap(args.limit)
    query = select(InboxConversation).where(
        InboxConversation.organization_id == ctx.organization_id,
        InboxConversation.archived_at.is_(None),
    )
    if args.query:
        term = f"%{args.query}%"
        query = query.where(
            or_(InboxConversation.subject.ilike(term), InboxConversation.channel.ilike(term))
        )
    rows = list(
        ctx.db.scalars(query.order_by(InboxConversation.updated_at.desc()).limit(size)).all()
    )
    payload_rows = [
        {"subject": row.subject, "channel": row.channel, "status": _enum(row.status)}
        for row in rows
    ]
    records = [
        _crm("inbox", row.id, row.subject, f"{row.channel}. {_enum(row.status)}") for row in rows
    ]
    payload: dict[str, Any] = {"conversations": payload_rows, "total": len(rows)}
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("search_inbox", payload, records)


def _analytics(ctx: ToolContext, _args: QueryArgs) -> ToolOutcome:
    data = snapshot(ctx.db, ctx.organization_id, scope=DataScope.all)
    qualification = data.get("qualification") if isinstance(data.get("qualification"), dict) else {}
    notice = data.get("provenance_notice")
    payload = {
        "companies_total": data.get("companies_total", 0),
        "leads_total": data.get("leads_total", 0),
        "inquiries_total": data.get("inquiries_total", 0),
        "open_leads": qualification.get("open", 0),
        "qualified_leads": qualification.get("qualified", 0),
        "failed_runs": data.get("failed_runs", 0),
        "notice": notice if isinstance(notice, str) else "",
    }
    record = _crm(
        "analytics",
        ctx.organization_id,
        "Workspace analytics",
        (
            f"{payload['companies_total']} companies, {payload['leads_total']} leads, "
            f"{payload['open_leads']} open"
        ),
    )
    return _ok("business_analytics", payload, [record])


def _knowledge(ctx: ToolContext, args: KnowledgeArgs) -> ToolOutcome:
    documents = [
        item
        for item in search_chunks(
            ctx.db,
            ctx.organization_id,
            args.query,
            ctx.embedder,
            limit=5,
            pipeline=PRODUCTION_PIPELINE,
        )
        if item.confidence >= 0.5
    ]
    payload = {
        "passages": [
            {"title": item.document_title, "excerpt": item.content[:400]} for item in documents
        ]
    }
    return ToolOutcome(
        name="search_knowledge",
        arguments={"query": args.query},
        status="succeeded",
        duration_ms=0,
        payload=payload,
        documents=documents,
        document_search="ready" if documents else "empty",
    )


def _availability(ctx: ToolContext, args: AvailabilityArgs) -> ToolOutcome:
    if args.starts_at is None or args.ends_at is None:
        return _ok("check_availability", {"needs_time": True, "available": None}, [])
    if not _valid_slot(args.starts_at, args.ends_at):
        return _failed_outcome(
            "check_availability",
            args.model_dump(mode="json"),
            "Choose a time range up to seven days.",
            "Ask for a start and end within seven days.",
        )
    available: bool | None = calendar_adapter().available(
        ctx.db, ctx.organization_id, args.starts_at, args.ends_at
    )
    provider = "workspace"
    recovery = None
    connected = False
    try:
        from app.integrations import google_calendar

        connection = google_calendar.active_connection(ctx.db, ctx.organization_id)
        if connection is not None:
            connected = True
            google_open = google_calendar.available(connection, args.starts_at, args.ends_at)
            available = bool(google_open and available)
            provider = "google"
    except AppError:
        if connected:
            available = None
            provider = "google"
            recovery = (
                "The connected calendar could not be checked. This slot was not treated as open."
            )
    payload = {
        "available": available,
        "provider": provider,
        "starts_at": args.starts_at.isoformat(),
        "ends_at": args.ends_at.isoformat(),
        "needs_time": False,
    }
    outcome = _ok("check_availability", payload, [])
    outcome.recovery = recovery
    return outcome


def _workflow_runs(ctx: ToolContext, args: WorkflowArgs) -> ToolOutcome:
    size = _cap(args.limit)
    query = select(WorkflowRun).where(WorkflowRun.organization_id == ctx.organization_id)
    if args.failed_only:
        query = query.where(WorkflowRun.status.in_(("failed", "needs_attention")))
    rows = list(ctx.db.scalars(query.order_by(WorkflowRun.created_at.desc()).limit(size)).all())
    payload_rows = [
        {
            "kind": _enum(row.kind),
            "status": _enum(row.status),
            "error": _clip(row.last_error),
            "attempts": row.attempt_count,
        }
        for row in rows
    ]
    records = [
        _crm("workflow_run", row.id, _enum(row.kind), _enum(row.status)) for row in rows
    ]
    payload: dict[str, Any] = {
        "runs": payload_rows,
        "total": len(rows),
        "failed_only": args.failed_only,
    }
    if args.limit is not None:
        payload["limited_to"] = size
    return _ok("list_workflow_runs", payload, records)


def _provider_health(ctx: ToolContext, _args: QueryArgs) -> ToolOutcome:
    from app.integrations.provider_status import connection_health, provider_status

    status = provider_status(ctx.db, ctx.organization_id)
    payload = status.model_dump(mode="json")
    payload["connections"] = connection_health(ctx.db, ctx.organization_id)
    return _ok("provider_health", payload, [])


def _draft(ctx: ToolContext, args: NamedArgs) -> ToolOutcome:
    return _proposal(ctx, Intent.follow_up, args.lead_name, "draft_customer_message")


def _appointment(ctx: ToolContext, args: NamedArgs) -> ToolOutcome:
    return _proposal(ctx, Intent.appointment, args.lead_name, "propose_appointment")


def _task(ctx: ToolContext, args: NamedArgs) -> ToolOutcome:
    return _proposal(ctx, Intent.task, args.lead_name, "propose_task")


def _proposal(ctx: ToolContext, intent: Intent, lead_name: str, tool_name: str) -> ToolOutcome:
    from app.domains.assistant.operations import prepare_operation, question_for_stored_lead

    name = lead_name.strip() or "the lead"
    question = question_for_stored_lead(
        ctx.db,
        ctx.organization_id,
        {
            Intent.follow_up: f"Draft a follow-up for {name}",
            Intent.appointment: f"Request an appointment for {name}",
            Intent.task: f"Create a follow-up task for {name}",
        }[intent],
        ctx.conversation_id,
    )
    read, draft = prepare_operation(ctx.db, ctx.organization_id, intent, question)
    records = list(read.crm_records)
    payload = {"summary": read.content, "proposed": draft is not None}
    outcome = _ok(tool_name, payload, records)
    outcome.proposal = draft
    return outcome


_TOOLS: list[tuple[str, str, type[BaseModel], Any]] = [
    (
        "list_companies",
        "List or search companies in this workspace. Set limit when the user asks for a count.",
        QueryArgs,
        _list_companies,
    ),
    ("list_contacts", "List or search contacts in this workspace.", QueryArgs, _list_contacts),
    (
        "list_leads",
        "List leads. Set needs_attention for new, contacted, or qualified leads.",
        LeadArgs,
        _list_leads,
    ),
    ("list_members", "List people who belong to this workspace.", QueryArgs, _list_members),
    (
        "list_opportunities",
        "List sales opportunities and pipeline stages.",
        QueryArgs,
        _list_opportunities,
    ),
    (
        "list_tasks",
        "List open tasks. Set overdue_only for tasks past their due time.",
        TaskArgs,
        _list_tasks,
    ),
    ("search_inbox", "Search inbox conversations in this workspace.", InboxArgs, _search_inbox),
    (
        "business_analytics",
        "Read counts for companies, leads, inquiries, and failures.",
        QueryArgs,
        _analytics,
    ),
    (
        "search_knowledge",
        "Search company documents. Use only for document questions.",
        KnowledgeArgs,
        _knowledge,
    ),
    (
        "check_availability",
        "Check whether a time range is open. Do not book it.",
        AvailabilityArgs,
        _availability,
    ),
    (
        "provider_health",
        "Read provider connection status for this workspace. Does not send or book.",
        QueryArgs,
        _provider_health,
    ),
    (
        "list_workflow_runs",
        "List workflow runs. failed_only limits the list to failures.",
        WorkflowArgs,
        _workflow_runs,
    ),
    ("draft_customer_message", "Draft a follow-up. It is not sent.", NamedArgs, _draft),
    ("propose_appointment", "Propose an appointment. It is not booked.", NamedArgs, _appointment),
    (
        "propose_task",
        "Propose a workspace task. It is not created until confirmed.",
        NamedArgs,
        _task,
    ),
]


def _ok(name: str, payload: dict[str, Any], records: list[dict[str, str]]) -> ToolOutcome:
    return ToolOutcome(
        name=name,
        arguments={},
        status="succeeded",
        duration_ms=0,
        payload=payload,
        records=records,
    )


def _failed(
    name: str,
    arguments: dict[str, Any],
    started: float,
    message: str,
    recovery: str | None,
) -> ToolOutcome:
    return ToolOutcome(
        name=name,
        arguments=arguments,
        status="failed",
        duration_ms=_elapsed(started),
        error_message=message[:500],
        recovery=recovery,
        payload={"summary": message[:500]},
    )


def _failed_outcome(
    name: str, arguments: dict[str, Any], message: str, recovery: str | None
) -> ToolOutcome:
    return ToolOutcome(
        name=name,
        arguments=arguments,
        status="failed",
        duration_ms=0,
        error_message=message[:500],
        recovery=recovery,
        payload={"summary": message[:500]},
    )


def _crm(kind: str, record_id: uuid.UUID, title: str, excerpt: str) -> dict[str, str]:
    return {
        "record_type": kind,
        "record_id": str(record_id),
        "title": title[:200],
        "excerpt": " ".join(excerpt.split())[:500],
    }


def _enum(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _clip(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())[:180]


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _valid_slot(starts_at: datetime, ends_at: datetime) -> bool:
    from datetime import timedelta

    span = ends_at - starts_at
    return timedelta(0) < span <= timedelta(days=7)
