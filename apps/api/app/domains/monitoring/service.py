import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.agents.models import AgentEvent, AgentRun, RunStatus
from app.domains.approvals.models import Approval, ApprovalStatus
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    ExecutionAttempt,
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.crm.models import Inquiry
from app.domains.observability.models import OperationTrace

_HINTS = {
    "callback_missing": "n8n acknowledged the lead event and no matching callback is stored.",
    "execution_uncertain": "The worker stopped before the external result was stored.",
    "llm_unconfigured": "The language model key is empty, so the run was stored as failed.",
    "interrupted": "The API restarted while this run was still marked running.",
    "n8n_timeout": "The n8n call timed out and was not sent again.",
    "smtp_timeout": "The SMTP result was uncertain and the message was not sent again.",
}


def diagnostics(db: Session, organization_id: uuid.UUID) -> dict[str, Any]:
    traces = list(
        db.scalars(
            select(OperationTrace)
            .where(OperationTrace.organization_id == organization_id)
            .order_by(OperationTrace.latency_ms.desc().nulls_last())
            .limit(50)
        )
    )
    failed_runs = list(
        db.scalars(
            select(AgentRun)
            .where(AgentRun.organization_id == organization_id, AgentRun.status == RunStatus.failed)
            .order_by(AgentRun.started_at.desc())
            .limit(20)
        )
    )
    attention = list(
        db.scalars(
            select(Approval)
            .where(
                Approval.organization_id == organization_id,
                Approval.status == ApprovalStatus.needs_attention,
            )
            .limit(20)
        )
    )
    workflow_failures = list(
        db.scalars(
            select(WorkflowRun)
            .where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.status.in_([WorkflowStatus.failed, WorkflowStatus.needs_attention]),
            )
            .order_by(WorkflowRun.created_at.desc())
            .limit(20)
        )
    )
    retries = int(
        db.scalar(
            select(func.count())
            .select_from(ExecutionAttempt)
            .where(
                ExecutionAttempt.organization_id == organization_id,
                ExecutionAttempt.outcome.in_(("failed", "uncertain")),
            )
        )
        or 0
    )
    costs = [trace.cost_usd for trace in traces if trace.cost_usd is not None]
    return {
        "hint_notice": "Hints name a recorded error code. They are not a root-cause finding.",
        "failed_runs": [
            {"id": run.id, "error_code": run.error_code, "hint": _HINTS.get(run.error_code or "")}
            for run in failed_runs
        ],
        "slowest_steps": [
            {
                "operation": trace.operation,
                "latency_ms": trace.latency_ms,
                "agent_run_id": trace.agent_run_id,
            }
            for trace in traces
            if trace.latency_ms is not None
        ][:5],
        "retries": retries,
        "needs_attention": [
            {"id": item.id, "action_type": item.action_type.value, "hint": None}
            for item in attention
        ],
        "integration_failures": [
            {
                "id": run.id,
                "status": run.status.value,
                "error": run.last_error,
                "hint": _HINTS.get(run.last_error or ""),
            }
            for run in workflow_failures
        ],
        "duration_buckets": _buckets(
            [trace.latency_ms for trace in traces if trace.latency_ms is not None]
        ),
        "cost_usd": None if not costs else round(sum(costs), 8),
        "cost_notice": (
            "Cost is unavailable unless token prices are configured "
            "and the provider reported usage."
        ),
    }


def trace_run(db: Session, organization_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    run = db.get(AgentRun, run_id)
    if run is None or run.organization_id != organization_id:
        raise AppError(404, "not_found", "Resource not found")
    inquiry = db.get(Inquiry, run.inquiry_id)
    events = list(
        db.scalars(
            select(AgentEvent)
            .where(AgentEvent.run_id == run.id, AgentEvent.organization_id == organization_id)
            .order_by(AgentEvent.created_at.asc())
        )
    )
    approvals = list(
        db.scalars(
            select(Approval)
            .where(Approval.run_id == run.id, Approval.organization_id == organization_id)
            .order_by(Approval.created_at.asc())
        )
    )
    workflows = list(
        db.scalars(
            select(WorkflowRun).where(
                WorkflowRun.agent_run_id == run.id,
                WorkflowRun.organization_id == organization_id,
            )
        )
    )
    traces = list(
        db.scalars(
            select(OperationTrace).where(
                OperationTrace.agent_run_id == run.id,
                OperationTrace.organization_id == organization_id,
            )
        )
    )
    lead_id = None if inquiry is None else inquiry.lead_id
    emails = []
    bookings = []
    if lead_id is not None:
        emails = list(
            db.scalars(
                select(EmailMessage).where(
                    EmailMessage.organization_id == organization_id,
                    EmailMessage.lead_id == lead_id,
                )
            )
        )
        bookings = list(
            db.scalars(
                select(CalendarBooking).where(
                    CalendarBooking.organization_id == organization_id,
                    CalendarBooking.lead_id == lead_id,
                )
            )
        )
    return {
        "hint_notice": "Hints name a recorded error code. They are not a root-cause finding.",
        "inquiry": None
        if inquiry is None
        else {"id": inquiry.id, "subject": inquiry.subject, "lead_id": inquiry.lead_id},
        "run": {
            "id": run.id,
            "status": run.status.value,
            "error_code": run.error_code,
            "hint": _HINTS.get(run.error_code or ""),
        },
        "events": [{"step": event.step, "status": event.status} for event in events],
        "approvals": [
            {"id": item.id, "action_type": item.action_type.value, "status": item.status.value}
            for item in approvals
        ],
        "workflows": [
            {
                "id": item.id,
                "status": item.status.value,
                "error": item.last_error,
                "hint": _HINTS.get(item.last_error or ""),
            }
            for item in workflows
        ],
        "traces": [
            {
                "operation": item.operation,
                "status": item.status,
                "latency_ms": item.latency_ms,
                "tokens_in": item.tokens_in,
                "tokens_out": item.tokens_out,
                "cost_usd": item.cost_usd,
                "error_code": item.error_code,
                "langfuse_status": item.langfuse_status,
            }
            for item in traces
        ],
        "emails": [
            {"id": item.id, "status": item.status.value, "mode": item.mode} for item in emails
        ],
        "bookings": [
            {"id": item.id, "status": item.status.value, "provider": item.provider}
            for item in bookings
        ],
    }


def _buckets(values: list[int]) -> list[dict[str, Any]]:
    bounds = [
        ("under_100ms", 0, 100),
        ("under_500ms", 100, 500),
        ("under_2s", 500, 2000),
        ("over_2s", 2000, None),
    ]
    buckets = []
    for name, low, high in bounds:
        count = sum(1 for value in values if value >= low and (high is None or value < high))
        buckets.append({"bucket": name, "count": count})
    return buckets
