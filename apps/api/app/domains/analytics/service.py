import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    EmailStatus,
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.crm.models import Inquiry, Interaction, Lead, LeadStatus
from app.domains.provenance.origin import DataScope, Origin, provenance_notice, scope_clause

WINDOW_DAYS = 30
OPEN_STATUSES = (LeadStatus.new, LeadStatus.contacted)
CLOSED_STATUSES = (LeadStatus.won, LeadStatus.lost)


def snapshot(
    db: Session, organization_id: uuid.UUID, scope: DataScope = DataScope.operational
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    start = datetime.combine(today - timedelta(days=WINDOW_DAYS - 1), datetime.min.time(), UTC)
    origins = _lead_origins(db, organization_id)
    return {
        "window_days": WINDOW_DAYS,
        "scope": scope.value,
        "lead_origins": origins,
        "provenance_notice": provenance_notice(scope, origins),
        "leads_total": _count(db, Lead, organization_id, scope),
        "inquiries_total": _count(db, Inquiry, organization_id, scope),
        "lead_status": _grouped(db, Lead.status, Lead, organization_id, scope),
        "qualification": {
            "qualified": _status_count(db, organization_id, (LeadStatus.qualified,), scope),
            "unqualified": _status_count(db, organization_id, (LeadStatus.unqualified,), scope),
            "open": _status_count(db, organization_id, OPEN_STATUSES, scope),
            "closed": _status_count(db, organization_id, CLOSED_STATUSES, scope),
            "definition": (
                "qualified and unqualified are those lead statuses. "
                "open is new or contacted. closed is won or lost."
            ),
        },
        "conversion": _conversion(db, organization_id, scope),
        "lead_trend": _trend(db, organization_id, start, today, scope),
        "agent_outcomes": _grouped(db, AgentRun.status, AgentRun, organization_id, scope),
        "failed_runs": failed_run_count(db, organization_id, scope),
        "approvals": _approvals(db, organization_id, scope),
        "automation": _automation(db, organization_id, scope),
        "follow_ups": _follow_ups(db, organization_id, scope),
        "email": _email(db, organization_id, scope),
        "calendar": _calendar(db, organization_id, scope),
    }


def _filters(model: Any, organization_id: uuid.UUID, scope: DataScope) -> list[Any]:
    filters = [model.organization_id == organization_id]
    clause = scope_clause(model.origin, scope)
    if clause is not None:
        filters.append(clause)
    return filters


def _lead_origins(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(Lead.origin, func.count())
        .where(Lead.organization_id == organization_id)
        .group_by(Lead.origin)
    ).all()
    counts = {item.value: 0 for item in Origin}
    for origin, count in rows:
        counts[_value(origin)] = int(count)
    return counts


def _count(db: Session, model: Any, organization_id: uuid.UUID, scope: DataScope) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(model).where(*_filters(model, organization_id, scope))
        )
        or 0
    )


def _grouped(
    db: Session, column: Any, model: Any, organization_id: uuid.UUID, scope: DataScope
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(column, func.count())
        .where(*_filters(model, organization_id, scope))
        .group_by(column)
        .order_by(column)
    ).all()
    return [{"status": _value(status), "count": int(count)} for status, count in rows]


def _status_count(
    db: Session, organization_id: uuid.UUID, statuses: tuple[LeadStatus, ...], scope: DataScope
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(*_filters(Lead, organization_id, scope), Lead.status.in_(statuses))
        )
        or 0
    )


def _conversion(db: Session, organization_id: uuid.UUID, scope: DataScope) -> dict[str, Any]:
    won = _status_count(db, organization_id, (LeadStatus.won,), scope)
    lost = _status_count(db, organization_id, (LeadStatus.lost,), scope)
    denominator = won + lost
    rate = None if denominator == 0 else round(won / denominator, 6)
    return {
        "won": won,
        "lost": lost,
        "denominator": denominator,
        "rate": rate,
        "definition": "won / (won + lost). Leads that are not won or lost are excluded.",
    }


def _trend(
    db: Session, organization_id: uuid.UUID, start: datetime, today: Any, scope: DataScope
) -> list[dict[str, Any]]:
    bucket = func.date_trunc("day", Lead.created_at)
    rows = db.execute(
        select(bucket, func.count())
        .where(*_filters(Lead, organization_id, scope), Lead.created_at >= start)
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    counts = {value.date(): int(count) for value, count in rows if value is not None}
    days = []
    cursor = start.date()
    while cursor <= today:
        days.append({"day": cursor.isoformat(), "count": counts.get(cursor, 0)})
        cursor += timedelta(days=1)
    return days


def _approvals(db: Session, organization_id: uuid.UUID, scope: DataScope) -> dict[str, int]:
    grouped = {
        item["status"]: item["count"]
        for item in _grouped(db, Approval.status, Approval, organization_id, scope)
    }
    pending = grouped.get(ApprovalStatus.pending.value, 0)
    completed = grouped.get(ApprovalStatus.executed.value, 0) + grouped.get(
        ApprovalStatus.rejected.value, 0
    )
    return {
        "pending": pending,
        "completed": completed,
        "needs_attention": grouped.get(ApprovalStatus.needs_attention.value, 0),
        "approved": grouped.get(ApprovalStatus.approved.value, 0),
        "executing": grouped.get(ApprovalStatus.executing.value, 0),
    }


def _automation(db: Session, organization_id: uuid.UUID, scope: DataScope) -> dict[str, Any]:
    grouped = {
        item["status"]: item["count"]
        for item in _grouped(db, WorkflowRun.status, WorkflowRun, organization_id, scope)
    }
    succeeded = grouped.get(WorkflowStatus.completed.value, 0)
    failed = grouped.get(WorkflowStatus.failed.value, 0) + grouped.get(
        WorkflowStatus.needs_attention.value, 0
    )
    total = succeeded + failed
    return {
        "succeeded": succeeded,
        "failed": failed,
        "other": sum(grouped.values()) - total,
        "success_rate": None if total == 0 else round(succeeded / total, 6),
        "definition": (
            "succeeded / (completed + failed + needs_attention). Other statuses are excluded."
        ),
    }


def _follow_ups(db: Session, organization_id: uuid.UUID, scope: DataScope) -> dict[str, int]:
    requested = int(
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                *_filters(Approval, organization_id, scope),
                Approval.action_type == ActionType.prepare_customer_response,
            )
        )
        or 0
    )
    interactions = _count(db, Interaction, organization_id, scope)
    return {"approval_requests": requested, "interactions": interactions}


def _email(db: Session, organization_id: uuid.UUID, scope: DataScope) -> dict[str, int]:
    rows = db.execute(
        select(EmailMessage.mode, EmailMessage.status, func.count())
        .where(*_filters(EmailMessage, organization_id, scope))
        .group_by(EmailMessage.mode, EmailMessage.status)
    ).all()
    sandbox = 0
    live = 0
    failed = 0
    for mode, status, count in rows:
        amount = int(count)
        if status == EmailStatus.failed:
            failed += amount
        if mode == "sandbox" and status == EmailStatus.sent:
            sandbox += amount
        if mode == "live" and status == EmailStatus.sent:
            live += amount
    return {"sandbox_sent": sandbox, "live_sent": live, "failed": failed}


def _calendar(db: Session, organization_id: uuid.UUID, scope: DataScope) -> dict[str, Any]:
    rows = db.execute(
        select(CalendarBooking.provider, CalendarBooking.status, func.count())
        .where(*_filters(CalendarBooking, organization_id, scope))
        .group_by(CalendarBooking.provider, CalendarBooking.status)
    ).all()
    booked = 0
    cancelled = 0
    providers = sorted({str(provider) for provider, _status, _count in rows})
    for _provider, status, count in rows:
        if status.value == "booked":
            booked += int(count)
        elif status.value == "cancelled":
            cancelled += int(count)
    return {
        "booked": booked,
        "cancelled": cancelled,
        "providers": providers,
        "notice": "Bookings from the simulation adapter are stored in ATLAS only.",
    }


def _value(status: Any) -> str:
    return str(status.value if hasattr(status, "value") else status)


def failed_run_count(
    db: Session, organization_id: uuid.UUID, scope: DataScope = DataScope.operational
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(*_filters(AgentRun, organization_id, scope), AgentRun.status == RunStatus.failed)
        )
        or 0
    )
