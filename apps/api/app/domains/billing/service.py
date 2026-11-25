import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.models import WorkflowRun, WorkflowStatus
from app.domains.billing.models import (
    OrganizationSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from app.domains.identity.models import Membership
from app.domains.knowledge.models import Document
from app.domains.observability.models import OperationTrace

PLAN_DEFINITIONS = {
    "free": {
        "name": "Free",
        "seats": 2,
        "ai_requests": 100,
        "knowledge_storage_bytes": 1_000_000_000,
        "active_workflows": 2,
    },
    "starter": {
        "name": "Starter",
        "seats": 5,
        "ai_requests": 1_000,
        "knowledge_storage_bytes": 10_000_000_000,
        "active_workflows": 10,
    },
    "pro": {
        "name": "Pro",
        "seats": 20,
        "ai_requests": 5_000,
        "knowledge_storage_bytes": 100_000_000_000,
        "active_workflows": 50,
    },
    "business": {
        "name": "Business",
        "seats": 100,
        "ai_requests": 25_000,
        "knowledge_storage_bytes": 1_000_000_000_000,
        "active_workflows": 200,
    },
}


def ensure_plans(db: Session) -> None:
    for code, definition in PLAN_DEFINITIONS.items():
        if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == code)) is None:
            db.add(SubscriptionPlan(code=code, name=definition["name"], entitlements=definition))
    db.flush()


def plan_for(db: Session, code: str) -> SubscriptionPlan:
    ensure_plans(db)
    row = db.scalar(
        select(SubscriptionPlan).where(
            SubscriptionPlan.code == code, SubscriptionPlan.active.is_(True)
        )
    )
    if row is None:
        raise AppError(400, "invalid_plan", "That subscription plan is unavailable")
    return row


def get_subscription(db: Session, organization_id: uuid.UUID) -> OrganizationSubscription:
    row = db.scalar(
        select(OrganizationSubscription).where(
            OrganizationSubscription.organization_id == organization_id
        )
    )
    if row is None:
        now = datetime.now(UTC)
        row = OrganizationSubscription(
            organization_id=organization_id,
            plan_code="free",
            billing_interval="monthly",
            status=SubscriptionStatus.active,
            provider="sandbox",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(row)
        db.flush()
    return row


def usage(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
    period_start = db.scalar(
        select(OrganizationSubscription.current_period_start).where(
            OrganizationSubscription.organization_id == organization_id
        )
    ) or datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    seats = (
        db.scalar(
            select(func.count(Membership.id)).where(Membership.organization_id == organization_id)
        )
        or 0
    )
    storage = (
        db.scalar(
            select(func.coalesce(func.sum(Document.byte_size), 0)).where(
                Document.organization_id == organization_id
            )
        )
        or 0
    )
    ai_requests = (
        db.scalar(
            select(func.count(OperationTrace.id)).where(
                OperationTrace.organization_id == organization_id,
                OperationTrace.operation.in_(["agent_run", "assistant"]),
                OperationTrace.started_at >= period_start,
            )
        )
        or 0
    )
    active_workflows = (
        db.scalar(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.status.in_(
                    [WorkflowStatus.pending, WorkflowStatus.dispatching, WorkflowStatus.accepted]
                ),
            )
        )
        or 0
    )
    return {
        "seats": int(seats),
        "ai_requests": int(ai_requests),
        "knowledge_storage_bytes": int(storage),
        "active_workflows": int(active_workflows),
    }


def enforce_limit(db: Session, organization_id: uuid.UUID, key: str, additional: int = 1) -> None:
    subscription = db.scalar(
        select(OrganizationSubscription)
        .where(OrganizationSubscription.organization_id == organization_id)
        .with_for_update()
    ) or get_subscription(db, organization_id)
    plan = plan_for(db, subscription.plan_code)
    current = usage(db, organization_id).get(key, 0)
    if current + additional > int(plan.entitlements.get(key, 0)):
        raise AppError(
            402,
            "entitlement_limit_reached",
            f"Your plan limit for {key.replace('_', ' ')} has been reached",
        )


def change_subscription(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, plan_code: str, interval: str
) -> OrganizationSubscription:
    if interval not in {"monthly", "yearly"}:
        raise AppError(400, "invalid_billing_interval", "Choose monthly or yearly billing")
    plan_for(db, plan_code)
    row = get_subscription(db, organization_id)
    row.plan_code, row.billing_interval, row.status = plan_code, interval, SubscriptionStatus.active
    row.provider = get_settings().billing_provider
    row.current_period_end = datetime.now(UTC) + (
        timedelta(days=365) if interval == "yearly" else timedelta(days=30)
    )
    row.current_period_start = datetime.now(UTC)
    record_event(
        db,
        organization_id,
        "subscription_changed",
        {"plan": plan_code, "interval": interval, "provider": row.provider},
        actor_id=actor_id,
    )
    db.commit()
    db.refresh(row)
    return row


def reconcile_provider_event(db: Session, payload: dict[str, object]) -> None:
    """Apply only provider-sourced subscription state; client requests never call this."""
    event_type = str(payload.get("type", ""))
    data = payload.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return
    subscription_id = str(obj.get("id", ""))
    customer_id = str(obj.get("customer", ""))
    row = None
    if subscription_id:
        row = db.scalar(
            select(OrganizationSubscription)
            .where(OrganizationSubscription.provider_subscription_id == subscription_id)
            .with_for_update()
        )
    if row is None and customer_id:
        row = db.scalar(
            select(OrganizationSubscription)
            .where(OrganizationSubscription.provider_customer_id == customer_id)
            .with_for_update()
        )
    if row is None:
        return
    status = str(obj.get("status", ""))
    if status in {item.value for item in SubscriptionStatus}:
        row.status = SubscriptionStatus(status)
    row.provider_subscription_id = subscription_id or row.provider_subscription_id
    row.provider_customer_id = customer_id or row.provider_customer_id
    period_start = obj.get("current_period_start")
    period_end = obj.get("current_period_end")
    if isinstance(period_start, int):
        row.current_period_start = datetime.fromtimestamp(period_start, UTC)
    if isinstance(period_end, int):
        row.current_period_end = datetime.fromtimestamp(period_end, UTC)
    if event_type == "invoice.payment_failed":
        row.status = SubscriptionStatus.past_due
    elif event_type == "invoice.payment_succeeded" and row.status == SubscriptionStatus.past_due:
        row.status = SubscriptionStatus.active
    elif event_type == "customer.subscription.deleted":
        row.status = SubscriptionStatus.canceled
