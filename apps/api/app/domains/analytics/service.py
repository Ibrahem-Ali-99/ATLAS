import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta
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
    WorkflowTask,
)
from app.domains.campaigns.models import Campaign, CampaignDelivery
from app.domains.crm.models import Company, Inquiry, Interaction, Lead, LeadStatus, Opportunity
from app.domains.inbox.models import InboxConversation, InboxMessage, InboxStatus
from app.domains.observability.models import EvaluationRun, OperationTrace
from app.domains.provenance.origin import DataScope, Origin, provenance_notice, scope_clause

WINDOW_DAYS = 30
OPEN_STATUSES = (LeadStatus.new, LeadStatus.contacted)
CLOSED_STATUSES = (LeadStatus.won, LeadStatus.lost)


def snapshot(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope = DataScope.operational,
    days: int = WINDOW_DAYS,
    start_date: date | None = None,
    end_date: date | None = None,
    owner_user_id: uuid.UUID | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    selected_start = start_date or today - timedelta(days=days - 1)
    selected_end = end_date or today
    start = datetime.combine(selected_start, datetime.min.time(), UTC)
    end = datetime.combine(selected_end, datetime.max.time(), UTC)
    origins = _lead_origins(db, organization_id)
    return {
        "window_days": days,
        "period": {"start": selected_start.isoformat(), "end": selected_end.isoformat()},
        "scope": scope.value,
        "lead_origins": origins,
        "provenance_notice": provenance_notice(scope, origins),
        "companies_total": _count(db, Company, organization_id, scope),
        "leads_total": _count(db, Lead, organization_id, scope),
        "inquiries_total": _count(db, Inquiry, organization_id, scope),
        "open_inquiries": _count(db, Inquiry, organization_id, scope),
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
        "lead_trend": [
            {"day": day.isoformat(), "count": count}
            for day, count in _daily_counts(db, Lead, organization_id, start, end, scope).items()
        ],
        "customer_activity": _customer_activity(db, organization_id, start, end, scope),
        "agent_outcomes": _grouped(db, AgentRun.status, AgentRun, organization_id, scope),
        "failed_runs": failed_run_count(db, organization_id, scope),
        "approvals": _approvals(db, organization_id, scope),
        "automation": _automation(db, organization_id, scope),
        "follow_ups": _follow_ups(db, organization_id, scope),
        "email": _email(db, organization_id, scope, start, end),
        "calendar": _calendar(db, organization_id, scope, start, end),
        "campaigns": _campaigns(db, organization_id, start, end),
        "qualification_trend": _qualification_trend(db, organization_id, scope, start, end),
        "comparison": _comparison(
            db, organization_id, scope, selected_start, selected_end, owner_user_id, channel
        ),
        "approval_activity": _approval_activity(db, organization_id, scope, start, end),
        "recent_interactions": _recent_interactions(db, organization_id, scope),
        "recent_agent_activity": _recent_agent_activity(db, organization_id, scope),
        "sales": _sales(db, organization_id, scope, owner_user_id, start, end),
        "support": _support(db, organization_id, scope, channel, start, end),
        "ai": _ai(db, organization_id, scope, start, end),
        "evaluation": _evaluation(db, organization_id, start, end),
        "workflow_performance": _workflow_performance(db, organization_id, start, end),
    }


def _sales(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    owner_user_id: uuid.UUID | None,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    filters = _filters(Opportunity, organization_id, scope) + [
        Opportunity.created_at >= start,
        Opportunity.created_at <= end,
    ]
    if owner_user_id:
        filters.append(Opportunity.owner_user_id == owner_user_id)
    opportunities_total = int(
        db.scalar(select(func.count()).select_from(Opportunity).where(*filters)) or 0
    )
    rows = db.execute(
        select(
            Opportunity.stage,
            Opportunity.currency,
            func.count(),
            func.count(Opportunity.value),
            func.coalesce(func.sum(Opportunity.value), 0),
        )
        .where(*filters)
        .group_by(Opportunity.stage, Opportunity.currency)
        .order_by(Opportunity.stage, Opportunity.currency)
    ).all()
    won = db.execute(
        select(func.count(), func.coalesce(func.sum(Opportunity.value), 0)).where(
            *filters, Opportunity.stage == "won"
        )
    ).one()
    lost = db.execute(
        select(func.count(), func.coalesce(func.sum(Opportunity.value), 0)).where(
            *filters, Opportunity.stage == "lost"
        )
    ).one()
    overdue = int(
        db.scalar(
            select(func.count())
            .select_from(WorkflowTask)
            .where(
                WorkflowTask.organization_id == organization_id,
                WorkflowTask.status != "completed",
                WorkflowTask.due_at.is_not(None),
                WorkflowTask.due_at < datetime.now(UTC),
            )
        )
        or 0
    )
    completed = int(
        db.scalar(
            select(func.count())
            .select_from(WorkflowTask)
            .where(
                WorkflowTask.organization_id == organization_id,
                WorkflowTask.status == "completed",
                WorkflowTask.updated_at >= start,
                WorkflowTask.updated_at <= end,
            )
        )
        or 0
    )
    won_count = int(won[0])
    lost_count = int(lost[0])
    closed = won_count + lost_count
    won_currencies = _won_currencies(db, filters)
    return {
        "opportunities_total": opportunities_total,
        "lead_to_opportunity": _lead_conversion(db, organization_id, scope, start, end),
        "win_rate": None if closed == 0 else round(won_count / closed, 6),
        "loss_rate": None if closed == 0 else round(lost_count / closed, 6),
        "average_won_value": _single_currency_average(won_currencies),
        "currencies": _currency_totals(db, filters),
        "won_by_currency": won_currencies,
        "stage_trend": _stage_trend(db, filters),
        "by_stage": [
            {
                "stage": stage,
                "currency": currency,
                "count": int(count),
                "value": None if int(valued) == 0 else float(total or 0),
            }
            for stage, currency, count, valued, total in rows
        ],
        "won": {"count": won_count, "value": None},
        "lost": {"count": lost_count, "value": None},
        "tasks_completed": completed,
        "tasks_overdue": overdue,
        "tasks_definition": (
            "Completed tasks are those marked completed whose record was last updated "
            "in the selected period. Overdue tasks are incomplete tasks whose deadline "
            "is already past, regardless of the selected period."
        ),
    }


def _lead_conversion(
    db: Session, organization_id: uuid.UUID, scope: DataScope, start: datetime, end: datetime
) -> dict[str, Any]:
    eligible = (
        select(Lead.id)
        .where(
            *_filters(Lead, organization_id, scope),
            Lead.created_at >= start,
            Lead.created_at <= end,
        )
        .subquery()
    )
    converted = int(
        db.scalar(
            select(func.count(func.distinct(Opportunity.lead_id))).where(
                Opportunity.organization_id == organization_id,
                Opportunity.archived_at.is_(None),
                Opportunity.lead_id.in_(select(eligible.c.id)),
                Opportunity.created_at >= start,
                Opportunity.created_at <= end,
            )
        )
        or 0
    )
    denominator = int(db.scalar(select(func.count()).select_from(eligible)) or 0)
    return {
        "eligible_leads": denominator,
        "converted_leads": converted,
        "rate": None if denominator == 0 else round(converted / denominator, 6),
        "definition": "distinct leads with an opportunity / leads created in the selected period",
    }


def _currency_totals(db: Session, filters: list[Any]) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Opportunity.currency,
            func.count(),
            func.count(Opportunity.value),
            func.coalesce(func.sum(Opportunity.value), 0),
        )
        .where(*filters)
        .group_by(Opportunity.currency)
    ).all()
    return [
        _currency_row(currency, count, valued, total) for currency, count, valued, total in rows
    ]


def _won_currencies(db: Session, filters: list[Any]) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Opportunity.currency,
            func.count(),
            func.count(Opportunity.value),
            func.coalesce(func.sum(Opportunity.value), 0),
        )
        .where(*filters, Opportunity.stage == "won")
        .group_by(Opportunity.currency)
    ).all()
    return [
        _currency_row(currency, count, valued, total) for currency, count, valued, total in rows
    ]


def _currency_row(currency: str, count: Any, valued: Any, total: Any) -> dict[str, Any]:
    return {
        "currency": currency,
        "count": int(count),
        "value": None if int(valued) == 0 else float(total or 0),
    }


def _single_currency_average(rows: list[dict[str, Any]]) -> float | None:
    valued = [row for row in rows if row["value"] is not None and row["count"]]
    if len(valued) != 1:
        return None
    return float(valued[0]["value"]) / int(valued[0]["count"])


def _stage_trend(db: Session, filters: list[Any]) -> list[dict[str, Any]]:
    day = func.date_trunc("day", Opportunity.created_at)
    rows = db.execute(
        select(
            day,
            Opportunity.stage,
            Opportunity.currency,
            func.count(),
            func.count(Opportunity.value),
            func.coalesce(func.sum(Opportunity.value), 0),
        )
        .where(*filters)
        .group_by(day, Opportunity.stage, Opportunity.currency)
        .order_by(day)
    ).all()
    return [
        {
            "day": item.date().isoformat(),
            "stage": stage,
            "currency": currency,
            "count": int(count),
            "value": None if int(valued) == 0 else float(total or 0),
        }
        for item, stage, currency, count, valued, total in rows
    ]


def _support(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    channel: str | None,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    filters = [
        InboxConversation.organization_id == organization_id,
        InboxConversation.created_at >= start,
        InboxConversation.created_at <= end,
    ]
    if channel:
        filters.append(InboxConversation.channel == channel)
    rows = db.execute(
        select(InboxConversation.channel, InboxConversation.status, func.count())
        .where(*filters)
        .group_by(InboxConversation.channel, InboxConversation.status)
    ).all()
    # Reuse the labeled expression in GROUP BY/ORDER BY. PostgreSQL treats
    # separately bound ``date_trunc`` arguments as distinct expressions even
    # when they have the same value, which otherwise raises a grouping error.
    trend_day = func.date_trunc("day", InboxConversation.created_at).label("day")
    trend = db.execute(
        select(trend_day, InboxConversation.channel, func.count())
        .where(*filters)
        .group_by(trend_day, InboxConversation.channel)
        .order_by(trend_day)
    ).all()
    conversation_ids = select(InboxConversation.id).where(*filters)
    inbound = (
        select(
            InboxMessage.conversation_id.label("conversation_id"),
            func.min(InboxMessage.created_at).label("opened_at"),
        )
        .where(
            InboxMessage.organization_id == organization_id,
            InboxMessage.conversation_id.in_(conversation_ids),
            InboxMessage.direction == "inbound",
        )
        .group_by(InboxMessage.conversation_id)
        .subquery()
    )
    responses = (
        select(
            func.extract("epoch", func.min(InboxMessage.created_at) - inbound.c.opened_at).label(
                "seconds"
            )
        )
        .select_from(inbound)
        .join(InboxMessage, InboxMessage.conversation_id == inbound.c.conversation_id)
        .where(
            InboxMessage.organization_id == organization_id,
            InboxMessage.direction == "outbound",
            InboxMessage.delivery_status.in_(["sent", "delivered", "read"]),
            InboxMessage.created_at >= inbound.c.opened_at,
            InboxMessage.created_at <= end,
        )
        .group_by(inbound.c.conversation_id, inbound.c.opened_at)
        .subquery()
    )
    average_response, response_count = db.execute(
        select(func.avg(responses.c.seconds), func.count()).select_from(responses)
    ).one()
    resolved = (
        select(
            func.extract(
                "epoch", InboxConversation.updated_at - InboxConversation.created_at
            ).label("seconds")
        )
        .where(
            *filters,
            InboxConversation.status == InboxStatus.resolved,
            InboxConversation.updated_at >= start,
            InboxConversation.updated_at <= end,
        )
        .subquery()
    )
    average_resolution, resolution_count = db.execute(
        select(func.avg(resolved.c.seconds), func.count()).select_from(resolved)
    ).one()
    return {
        "by_channel": [
            {
                "channel": str(channel),
                "status": str(status.value if hasattr(status, "value") else status),
                "count": int(count),
            }
            for channel, status, count in rows
        ],
        "handoffs": int(
            db.scalar(
                select(func.count())
                .select_from(InboxConversation)
                .where(
                    *filters,
                    InboxConversation.handoff_requested.is_(True),
                )
            )
            or 0
        ),
        "volume_trend": [
            {"day": item.date().isoformat(), "channel": str(name), "count": int(count)}
            for item, name, count in trend
        ],
        "average_first_response_seconds": None
        if average_response is None
        else round(float(average_response), 1),
        "first_response_sample_size": int(response_count),
        "average_resolution_seconds": None
        if average_resolution is None
        else round(float(average_resolution), 1),
        "resolution_sample_size": int(resolution_count),
        "resolution_definition": (
            "Average of last update minus creation for conversations whose current "
            "status is resolved and whose last update is in the selected period. "
            "A later edit changes this duration."
        ),
    }


def _ai(
    db: Session, organization_id: uuid.UUID, scope: DataScope, start: datetime, end: datetime
) -> dict[str, Any]:
    rows = db.execute(
        select(OperationTrace.status, func.count())
        .where(
            OperationTrace.organization_id == organization_id,
            OperationTrace.operation.in_(["assistant_response", "agent_run"]),
            OperationTrace.started_at >= start,
            OperationTrace.started_at <= end,
        )
        .group_by(OperationTrace.status)
    ).all()
    total = sum(int(row[1]) for row in rows)
    failed = sum(int(row[1]) for row in rows if str(row[0]).lower() in {"failed", "error"})
    day = func.date_trunc("day", OperationTrace.started_at).label("day")
    trend_rows = db.execute(
        select(day, OperationTrace.status, func.count())
        .where(
            OperationTrace.organization_id == organization_id,
            OperationTrace.operation.in_(["assistant_response", "agent_run"]),
            OperationTrace.started_at >= start,
            OperationTrace.started_at <= end,
        )
        .group_by(day, OperationTrace.status)
        .order_by(day)
    ).all()
    return {
        "requests": total,
        "failed": failed,
        "failure_rate": None if total == 0 else round(failed / total, 6),
        "trend": [
            {"day": item.date().isoformat(), "status": str(status), "count": int(count)}
            for item, status, count in trend_rows
        ],
    }


def _evaluation(
    db: Session, organization_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    executed = int(
        db.scalar(
            select(func.sum(EvaluationRun.executed_count)).where(
                EvaluationRun.organization_id == organization_id,
                EvaluationRun.created_at >= start,
                EvaluationRun.created_at <= end,
            )
        )
        or 0
    )
    passed = int(
        db.scalar(
            select(func.sum(EvaluationRun.passed_count)).where(
                EvaluationRun.organization_id == organization_id,
                EvaluationRun.created_at >= start,
                EvaluationRun.created_at <= end,
            )
        )
        or 0
    )
    return {
        "executed": executed,
        "passed": passed,
        "pass_rate": None if executed == 0 else round(passed / executed, 6),
    }


def _workflow_performance(
    db: Session, organization_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    filters = [
        WorkflowRun.organization_id == organization_id,
        WorkflowRun.created_at >= start,
        WorkflowRun.created_at <= end,
    ]
    grouped = db.execute(
        select(WorkflowRun.status, func.count()).where(*filters).group_by(WorkflowRun.status)
    ).all()
    counts = {
        str(status.value if hasattr(status, "value") else status): int(count)
        for status, count in grouped
    }
    successful = counts.get(WorkflowStatus.completed.value, 0)
    failed = counts.get(WorkflowStatus.failed.value, 0) + counts.get(
        WorkflowStatus.needs_attention.value, 0
    )
    terminal = successful + failed
    day = func.date_trunc("day", WorkflowRun.created_at).label("day")
    trend_rows = db.execute(
        select(day, WorkflowRun.status, func.count())
        .where(*filters)
        .group_by(day, WorkflowRun.status)
        .order_by(day)
    ).all()
    return {
        "total": sum(counts.values()),
        "successful": successful,
        "failed": failed,
        "pending": counts.get(WorkflowStatus.pending.value, 0),
        "running": counts.get(WorkflowStatus.dispatching.value, 0),
        "success_rate": None if terminal == 0 else round(successful / terminal, 6),
        "denominator": terminal,
        "trend": [
            {
                "day": item.date().isoformat(),
                "status": str(status.value if hasattr(status, "value") else status),
                "count": int(count),
            }
            for item, status, count in trend_rows
        ],
    }


def _filters(model: Any, organization_id: uuid.UUID, scope: DataScope) -> list[Any]:
    filters = [model.organization_id == organization_id]
    if hasattr(model, "archived_at"):
        filters.append(model.archived_at.is_(None))
    clause = scope_clause(model.origin, scope) if hasattr(model, "origin") else None
    if clause is not None:
        filters.append(clause)
    return filters


def _lead_origins(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(Lead.origin, func.count())
        .where(Lead.organization_id == organization_id, Lead.archived_at.is_(None))
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


def _daily_counts(
    db: Session,
    model: type[Lead] | type[Inquiry] | type[Interaction],
    organization_id: uuid.UUID,
    start: datetime,
    end: datetime,
    scope: DataScope,
) -> dict[date, int]:
    bucket = func.date_trunc("day", func.timezone("UTC", model.created_at))
    rows = db.execute(
        select(bucket, func.count())
        .where(*_filters(model, organization_id, scope), model.created_at.between(start, end))
        .group_by(bucket)
    ).all()
    counts = {value.date(): int(count) for value, count in rows if value is not None}
    days = (start.date() + timedelta(days=index) for index in range((end - start).days + 1))
    return {day: counts.get(day, 0) for day in days}


def _customer_activity(
    db: Session, organization_id: uuid.UUID, start: datetime, end: datetime, scope: DataScope
) -> list[dict[str, str | int]]:
    inquiries = _daily_counts(db, Inquiry, organization_id, start, end, scope)
    interactions = _daily_counts(db, Interaction, organization_id, start, end, scope)
    return [
        {"day": day.isoformat(), "inquiries": count, "interactions": interactions[day]}
        for day, count in inquiries.items()
    ]


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


def _email(
    db: Session, organization_id: uuid.UUID, scope: DataScope, start: datetime, end: datetime
) -> dict[str, int]:
    rows = db.execute(
        select(EmailMessage.mode, EmailMessage.status, func.count())
        .where(
            *_filters(EmailMessage, organization_id, scope),
            EmailMessage.created_at >= start,
            EmailMessage.created_at <= end,
        )
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


def _calendar(
    db: Session, organization_id: uuid.UUID, scope: DataScope, start: datetime, end: datetime
) -> dict[str, Any]:
    rows = db.execute(
        select(CalendarBooking.provider, CalendarBooking.status, func.count())
        .where(
            *_filters(CalendarBooking, organization_id, scope),
            CalendarBooking.starts_at >= start,
            CalendarBooking.starts_at <= end,
        )
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


def _recent_interactions(
    db: Session, organization_id: uuid.UUID, scope: DataScope
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Interaction)
        .where(*_filters(Interaction, organization_id, scope))
        .order_by(Interaction.created_at.desc())
        .limit(5)
    ).all()
    return [
        {
            "id": str(item.id),
            "lead_id": str(item.lead_id),
            "kind": item.kind.value,
            "summary": item.body[:140],
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]


def _recent_agent_activity(
    db: Session, organization_id: uuid.UUID, scope: DataScope
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AgentRun)
        .where(*_filters(AgentRun, organization_id, scope))
        .order_by(AgentRun.updated_at.desc())
        .limit(5)
    ).all()
    return [
        {
            "id": str(item.id),
            "status": item.status.value,
            "inquiry_id": str(item.inquiry_id),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in rows
    ]


def _comparison(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    start_date: date,
    end_date: date,
    owner_user_id: uuid.UUID | None,
    channel: str | None,
) -> dict[str, Any]:
    length = (end_date - start_date).days
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=length)
    current = _window_counts(
        db, organization_id, scope, start_date, end_date, owner_user_id, channel
    )
    previous = _window_counts(
        db, organization_id, scope, previous_start, previous_end, owner_user_id, channel
    )
    return {
        "previous_period": {"start": previous_start.isoformat(), "end": previous_end.isoformat()},
        "leads_created": _delta(current["leads_created"], previous["leads_created"]),
        "opportunities_created": _delta(
            current["opportunities_created"], previous["opportunities_created"]
        ),
        "conversations": _delta(current["conversations"], previous["conversations"]),
        "opportunities_won": _delta(current["opportunities_won"], previous["opportunities_won"]),
    }


def _window_counts(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    start_date: date,
    end_date: date,
    owner_user_id: uuid.UUID | None,
    channel: str | None,
) -> dict[str, int]:
    start = datetime.combine(start_date, datetime.min.time(), UTC)
    end = datetime.combine(end_date, datetime.max.time(), UTC)
    opportunity_filters = [
        *_filters(Opportunity, organization_id, scope),
        Opportunity.created_at >= start,
        Opportunity.created_at <= end,
    ]
    if owner_user_id is not None:
        opportunity_filters.append(Opportunity.owner_user_id == owner_user_id)
    conversation_filters = [
        InboxConversation.organization_id == organization_id,
        InboxConversation.created_at >= start,
        InboxConversation.created_at <= end,
    ]
    if channel:
        conversation_filters.append(InboxConversation.channel == channel)
    return {
        "leads_created": _bounded_count(db, Lead, organization_id, scope, start, end),
        "opportunities_created": int(
            db.scalar(select(func.count()).select_from(Opportunity).where(*opportunity_filters))
            or 0
        ),
        "conversations": int(
            db.scalar(
                select(func.count()).select_from(InboxConversation).where(*conversation_filters)
            )
            or 0
        ),
        "opportunities_won": int(
            db.scalar(
                select(func.count())
                .select_from(Opportunity)
                .where(*opportunity_filters, Opportunity.stage == "won")
            )
            or 0
        ),
    }


def _bounded_count(
    db: Session,
    model: Any,
    organization_id: uuid.UUID,
    scope: DataScope,
    start: datetime,
    end: datetime,
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(
                *_filters(model, organization_id, scope),
                model.created_at >= start,
                model.created_at <= end,
            )
        )
        or 0
    )


def _delta(current: int, previous: int) -> dict[str, int | float | None]:
    return {
        "current": current,
        "previous": previous,
        "delta": current - previous,
        "change_rate": None if previous == 0 else round((current - previous) / previous, 6),
    }


def _qualification_trend(
    db: Session, organization_id: uuid.UUID, scope: DataScope, start: datetime, end: datetime
) -> list[dict[str, str | int]]:
    bucket = func.date_trunc("day", func.timezone("UTC", Lead.created_at))
    rows = db.execute(
        select(bucket, Lead.status, func.count())
        .where(
            *_filters(Lead, organization_id, scope),
            Lead.created_at >= start,
            Lead.created_at <= end,
        )
        .group_by(bucket, Lead.status)
    ).all()
    created: dict[date, int] = {}
    qualified: dict[date, int] = {}
    for value, status, count in rows:
        if value is None:
            continue
        day = value.date()
        created[day] = created.get(day, 0) + int(count)
        if _value(status) == LeadStatus.qualified.value:
            qualified[day] = qualified.get(day, 0) + int(count)
    days = (start.date() + timedelta(days=index) for index in range((end - start).days + 1))
    return [
        {"day": day.isoformat(), "created": created.get(day, 0), "qualified": qualified.get(day, 0)}
        for day in days
    ]


def _campaigns(
    db: Session, organization_id: uuid.UUID, start: datetime, end: datetime
) -> dict[str, Any]:
    campaign_ids = select(Campaign.id).where(
        Campaign.organization_id == organization_id,
        Campaign.created_at >= start,
        Campaign.created_at <= end,
    )
    campaigns = int(db.scalar(select(func.count()).select_from(campaign_ids.subquery())) or 0)
    rows = db.execute(
        select(CampaignDelivery.status, func.count())
        .where(CampaignDelivery.campaign_id.in_(campaign_ids))
        .group_by(CampaignDelivery.status)
        .order_by(CampaignDelivery.status)
    ).all()
    return {
        "campaigns": campaigns,
        "deliveries": [{"status": str(status), "count": int(count)} for status, count in rows],
        "definition": (
            "Delivery outcomes for campaigns created in the selected period. "
            "Open and click events are not stored."
        ),
    }


def _approval_activity(
    db: Session, organization_id: uuid.UUID, scope: DataScope, start: datetime, end: datetime
) -> dict[str, Any]:
    rows = db.execute(
        select(Approval.status, func.count())
        .where(
            *_filters(Approval, organization_id, scope),
            Approval.created_at >= start,
            Approval.created_at <= end,
        )
        .group_by(Approval.status)
        .order_by(Approval.status)
    ).all()
    by_status = [{"status": _value(status), "count": int(count)} for status, count in rows]
    return {
        "created": sum(item["count"] for item in by_status),
        "by_status": by_status,
        "definition": "Approvals created in the selected period. Pending now is the current queue.",
    }


def report_csv(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    report: str,
    start: datetime,
    end: datetime,
    owner_user_id: uuid.UUID | None,
    channel: str | None,
) -> tuple[str, str]:
    headers, rows = _report_rows(
        db, organization_id, scope, report, start, end, owner_user_id, channel
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    filename = f"atlas-{report}-{start.date().isoformat()}-{end.date().isoformat()}.csv"
    return filename, buffer.getvalue()


def _report_rows(
    db: Session,
    organization_id: uuid.UUID,
    scope: DataScope,
    report: str,
    start: datetime,
    end: datetime,
    owner_user_id: uuid.UUID | None,
    channel: str | None,
) -> tuple[list[str], list[list[str]]]:
    if report == "leads":
        rows = db.scalars(
            select(Lead)
            .where(
                *_filters(Lead, organization_id, scope),
                Lead.created_at >= start,
                Lead.created_at <= end,
            )
            .order_by(Lead.created_at)
            .limit(5000)
        ).all()
        return ["title", "status", "source", "created_at"], [
            [item.title, item.status.value, item.source or "", item.created_at.isoformat()]
            for item in rows
        ]
    if report == "opportunities":
        filters = [
            *_filters(Opportunity, organization_id, scope),
            Opportunity.created_at >= start,
            Opportunity.created_at <= end,
        ]
        if owner_user_id is not None:
            filters.append(Opportunity.owner_user_id == owner_user_id)
        rows = db.scalars(
            select(Opportunity).where(*filters).order_by(Opportunity.created_at).limit(5000)
        ).all()
        return ["title", "stage", "currency", "value", "created_at"], [
            [
                item.title,
                item.stage,
                item.currency,
                "" if item.value is None else str(item.value),
                item.created_at.isoformat(),
            ]
            for item in rows
        ]
    if report == "conversations":
        filters = [
            InboxConversation.organization_id == organization_id,
            InboxConversation.created_at >= start,
            InboxConversation.created_at <= end,
        ]
        if channel:
            filters.append(InboxConversation.channel == channel)
        rows = db.scalars(
            select(InboxConversation)
            .where(*filters)
            .order_by(InboxConversation.created_at)
            .limit(5000)
        ).all()
        return ["subject", "channel", "status", "created_at"], [
            [item.subject, item.channel, item.status.value, item.created_at.isoformat()]
            for item in rows
        ]
    if report == "tasks":
        rows = db.scalars(
            select(WorkflowTask)
            .where(
                WorkflowTask.organization_id == organization_id,
                WorkflowTask.created_at >= start,
                WorkflowTask.created_at <= end,
            )
            .order_by(WorkflowTask.created_at)
            .limit(5000)
        ).all()
        return ["title", "status", "priority", "due_at"], [
            [
                item.title,
                item.status,
                item.priority,
                "" if item.due_at is None else item.due_at.isoformat(),
            ]
            for item in rows
        ]
    if report == "appointments":
        rows = db.scalars(
            select(CalendarBooking)
            .where(
                *_filters(CalendarBooking, organization_id, scope),
                CalendarBooking.starts_at >= start,
                CalendarBooking.starts_at <= end,
            )
            .order_by(CalendarBooking.starts_at)
            .limit(5000)
        ).all()
        return ["status", "starts_at", "ends_at"], [
            [item.status.value, item.starts_at.isoformat(), item.ends_at.isoformat()]
            for item in rows
        ]
    if report == "campaigns":
        payload = _campaigns(db, organization_id, start, end)
        return ["status", "count"], [
            [str(item["status"]), str(item["count"])] for item in payload["deliveries"]
        ]
    if report == "workflows":
        rows = db.scalars(
            select(WorkflowRun)
            .where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.created_at >= start,
                WorkflowRun.created_at <= end,
            )
            .order_by(WorkflowRun.created_at)
            .limit(5000)
        ).all()
        return ["status", "created_at"], [
            [_value(item.status), item.created_at.isoformat()] for item in rows
        ]
    rows = db.scalars(
        select(Approval)
        .where(
            *_filters(Approval, organization_id, scope),
            Approval.created_at >= start,
            Approval.created_at <= end,
        )
        .order_by(Approval.created_at)
        .limit(5000)
    ).all()
    return ["action", "status", "created_at"], [
        [_value(item.action_type), _value(item.status), item.created_at.isoformat()]
        for item in rows
    ]
