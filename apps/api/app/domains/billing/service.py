import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.models import WorkflowDefinition, WorkflowRun, WorkflowStatus
from app.domains.billing import provider
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
    existing = set(db.scalars(select(SubscriptionPlan.code)))
    missing = [
        {"code": code, "name": definition["name"], "entitlements": definition}
        for code, definition in PLAN_DEFINITIONS.items()
        if code not in existing
    ]
    if missing:
        db.execute(
            insert(SubscriptionPlan)
            .values(missing)
            .on_conflict_do_nothing(index_elements=[SubscriptionPlan.code])
        )


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


def get_subscription(
    db: Session, organization_id: uuid.UUID, *, lock: bool = False
) -> OrganizationSubscription:
    query = select(OrganizationSubscription).where(
        OrganizationSubscription.organization_id == organization_id
    )
    if lock:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is not None:
        return row
    now = datetime.now(UTC)
    db.execute(
        insert(OrganizationSubscription)
        .values(
            organization_id=organization_id,
            plan_code="free",
            billing_interval="monthly",
            status=SubscriptionStatus.active,
            provider="sandbox",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        .on_conflict_do_nothing(index_elements=[OrganizationSubscription.organization_id])
    )
    return db.scalars(query).one()


def entitlement_plan_code(row: OrganizationSubscription) -> str:
    if row.status not in {SubscriptionStatus.active, SubscriptionStatus.trialing}:
        return "free"
    return row.plan_code


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
                OperationTrace.operation.in_(
                    ["agent_run", "assistant", "metered_assistant_request"]
                ),
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
    subscription = get_subscription(db, organization_id, lock=True)
    plan = plan_for(db, entitlement_plan_code(subscription))
    current = usage(db, organization_id).get(key, 0)
    if current + additional > int(plan.entitlements.get(key, 0)):
        raise AppError(
            402,
            "entitlement_limit_reached",
            f"Your plan limit for {key.replace('_', ' ')} has been reached",
        )


def enforce_workflow_definition_limit(db: Session, organization_id: uuid.UUID) -> None:
    subscription = get_subscription(db, organization_id, lock=True)
    plan = plan_for(db, entitlement_plan_code(subscription))
    current = (
        db.scalar(
            select(func.count())
            .select_from(WorkflowDefinition)
            .where(
                WorkflowDefinition.organization_id == organization_id,
                WorkflowDefinition.active.is_(True),
            )
        )
        or 0
    )
    if current >= int(plan.entitlements.get("active_workflows", 0)):
        raise AppError(
            402,
            "entitlement_limit_reached",
            "Your plan limit for active workflows has been reached",
        )


def meter_assistant_request(db: Session, organization_id: uuid.UUID) -> None:
    enforce_limit(db, organization_id, "ai_requests")
    now = datetime.now(UTC)
    db.add(
        OperationTrace(
            organization_id=organization_id,
            operation="metered_assistant_request",
            status="accepted",
            started_at=now,
            finished_at=now,
        )
    )
    db.commit()


def change_subscription(
    db: Session, organization_id: uuid.UUID, actor_id: uuid.UUID, plan_code: str, interval: str
) -> OrganizationSubscription:
    if get_settings().billing_provider != "sandbox":
        raise AppError(
            409, "provider_managed_subscription", "The payment provider manages this subscription"
        )
    if interval not in {"monthly", "yearly"}:
        raise AppError(400, "invalid_billing_interval", "Choose monthly or yearly billing")
    plan_for(db, plan_code)
    row = get_subscription(db, organization_id, lock=True)
    if row.provider != "sandbox":
        raise AppError(
            409, "provider_managed_subscription", "The payment provider manages this subscription"
        )
    if row.plan_code == plan_code and row.billing_interval == interval:
        db.commit()
        return row
    row.plan_code, row.billing_interval, row.status = plan_code, interval, SubscriptionStatus.active
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
    event_type = payload.get("type")
    if event_type not in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        return
    data = payload.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return
    from_checkout = str(event_type).startswith("checkout.")
    if from_checkout and obj.get("payment_status") not in ("paid", "no_payment_required"):
        return
    subscription_id = obj.get("subscription" if from_checkout else "id")
    customer_id = obj.get("customer")
    if not isinstance(subscription_id, str) or not isinstance(customer_id, str):
        return
    row = db.scalar(
        select(OrganizationSubscription)
        .where(OrganizationSubscription.provider_customer_id == customer_id)
        .with_for_update()
    )
    if row is None:
        return
    if from_checkout and obj.get("client_reference_id") != str(row.organization_id):
        return
    current = provider.retrieve_subscription(subscription_id)
    if current.get("customer") != customer_id or current.get("livemode") is not False:
        raise AppError(
            409, "billing_subscription_mismatch", "Stripe subscription ownership differs"
        )
    metadata = current.get("metadata")
    same_subscription = row.provider_subscription_id == subscription_id
    if not same_subscription:
        if not isinstance(metadata, dict) or metadata.get("atlas_organization") != str(
            row.organization_id
        ):
            return
        if row.provider_subscription_id and row.status not in {
            SubscriptionStatus.canceled,
            SubscriptionStatus.expired,
        }:
            return
        if current.get("status") not in {"active", "trialing"}:
            return

    provider_status = str(current.get("status", ""))
    status = {
        "active": SubscriptionStatus.active,
        "trialing": SubscriptionStatus.trialing,
        "past_due": SubscriptionStatus.past_due,
        "unpaid": SubscriptionStatus.past_due,
        "paused": SubscriptionStatus.past_due,
        "canceled": SubscriptionStatus.canceled,
        "incomplete": SubscriptionStatus.expired,
        "incomplete_expired": SubscriptionStatus.expired,
    }.get(provider_status)
    if status is None:
        raise AppError(
            502, "billing_status_unknown", "The payment provider returned an unknown status"
        )
    items = current.get("items")
    lines = items.get("data") if isinstance(items, dict) else None
    if not isinstance(lines, list) or len(lines) != 1 or not isinstance(lines[0], dict):
        raise AppError(409, "billing_price_unavailable", "This subscription must have one plan")
    item = lines[0]
    price = item.get("price")
    price_id = price.get("id") if isinstance(price, dict) else None
    selections = [key for key, value in provider.price_map().items() if value == price_id]
    if len(selections) != 1:
        raise AppError(
            409, "billing_price_unavailable", "The Stripe price is not mapped to one plan"
        )
    code, sep, interval = selections[0].partition(":")
    if not sep or interval not in {"monthly", "yearly"}:
        raise AppError(409, "billing_price_unavailable", "The Stripe billing interval is invalid")
    plan_for(db, code)
    period_start = item.get("current_period_start", current.get("current_period_start"))
    period_end = item.get("current_period_end", current.get("current_period_end"))
    if type(period_start) is not int or type(period_end) is not int or period_start >= period_end:
        raise AppError(
            409, "billing_period_unavailable", "The payment provider returned an invalid period"
        )
    changed = (row.plan_code, row.billing_interval, row.status, row.provider_subscription_id)
    row.plan_code = code
    row.billing_interval = interval
    row.status = status
    row.provider = "stripe"
    row.provider_subscription_id = subscription_id
    row.current_period_start = datetime.fromtimestamp(period_start, UTC)
    row.current_period_end = datetime.fromtimestamp(period_end, UTC)
    if changed != (code, interval, status, subscription_id):
        record_event(
            db,
            row.organization_id,
            "stripe_subscription_reconciled",
            {
                "plan": code,
                "interval": interval,
                "status": status.value,
            },
        )
