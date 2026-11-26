import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.models import AuditEvent
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

# A delayed renewal webhook can arrive after the recorded period ends. Keep the
# paid Stripe plan for this long, then use Free limits until Stripe confirms the
# next period. Sandbox periods are not expired locally.
STRIPE_RENEWAL_GRACE = timedelta(hours=2)

_CHECKOUT_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
}
_SUBSCRIPTION_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}
_INVOICE_EVENTS = {
    "invoice.paid",
    "invoice.payment_failed",
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
    # Trialing, past due, canceled, and expired are not confirmed payment.
    if row.status != SubscriptionStatus.active:
        return "free"
    period_end = row.current_period_end
    if (
        row.provider == "stripe"
        and period_end is not None
        and period_end <= datetime.now(UTC) - STRIPE_RENEWAL_GRACE
    ):
        return "free"
    return row.plan_code


def scheduled_cancellation(db: Session, organization_id: uuid.UUID) -> bool:
    details = db.scalar(
        select(AuditEvent.details)
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.action == "stripe_subscription_reconciled",
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    return isinstance(details, dict) and details.get("cancels_at_period_end") is True


def billing_attention(row: OrganizationSubscription, cancels_at_period_end: bool) -> str | None:
    if row.status == SubscriptionStatus.past_due:
        return "payment_failed"
    if row.status == SubscriptionStatus.canceled:
        return "canceled"
    if row.status == SubscriptionStatus.expired:
        return "expired"
    if row.status == SubscriptionStatus.trialing:
        return "payment_unconfirmed"
    if cancels_at_period_end:
        return "cancels_at_period_end"
    if entitlement_plan_code(row) != row.plan_code:
        return "period_lapsed"
    return None


def checkout_available(row: OrganizationSubscription) -> bool:
    if get_settings().billing_provider != "stripe":
        return True
    if row.provider != "stripe" or not row.provider_subscription_id:
        return True
    if row.status in {SubscriptionStatus.past_due, SubscriptionStatus.trialing}:
        return False
    if row.status in {SubscriptionStatus.canceled, SubscriptionStatus.expired}:
        return True
    return entitlement_plan_code(row) == "free" and row.plan_code != "free"


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
    if not isinstance(event_type, str) or event_type not in (
        _CHECKOUT_EVENTS | _SUBSCRIPTION_EVENTS | _INVOICE_EVENTS
    ):
        return
    data = payload.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return
    # Checkout can finish before Stripe collects payment. Leave the current plan
    # in place until a later event retrieves an active subscription.
    if event_type in _CHECKOUT_EVENTS and obj.get("payment_status") not in (
        "paid",
        "no_payment_required",
    ):
        return
    subscription_id = _provider_subscription_id(event_type, obj)
    customer_id = _stripe_id(obj.get("customer"))
    if subscription_id is None or customer_id is None:
        return
    row = db.scalar(
        select(OrganizationSubscription)
        .where(OrganizationSubscription.provider_customer_id == customer_id)
        .with_for_update()
    )
    if row is None:
        return
    reference = obj.get("client_reference_id")
    if event_type in _CHECKOUT_EVENTS and reference != str(row.organization_id):
        return
    # The event names the subscription. The live Stripe subscription decides the
    # plan, period, and status, so an older event cannot restore a replaced one.
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
        if current.get("status") != "active":
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
    cancels = _cancels_at_period_end(current)
    previous_cancel = scheduled_cancellation(db, row.organization_id)
    snapshot = (
        row.plan_code,
        row.billing_interval,
        row.status,
        row.provider_subscription_id,
        previous_cancel,
    )
    row.plan_code = code
    row.billing_interval = interval
    row.status = status
    row.provider = "stripe"
    row.provider_subscription_id = subscription_id
    row.current_period_start = datetime.fromtimestamp(period_start, UTC)
    row.current_period_end = datetime.fromtimestamp(period_end, UTC)
    if snapshot != (code, interval, status, subscription_id, cancels):
        record_event(
            db,
            row.organization_id,
            "stripe_subscription_reconciled",
            {
                "plan": code,
                "interval": interval,
                "status": status.value,
                "cancels_at_period_end": cancels,
            },
        )


def _provider_subscription_id(event_type: str, obj: dict[str, object]) -> str | None:
    if event_type in _CHECKOUT_EVENTS:
        return _stripe_id(obj.get("subscription"))
    if event_type in _INVOICE_EVENTS:
        direct = _stripe_id(obj.get("subscription"))
        if direct is not None:
            return direct
        parent = obj.get("parent")
        if not isinstance(parent, dict):
            return None
        details = parent.get("subscription_details")
        if not isinstance(details, dict):
            return None
        return _stripe_id(details.get("subscription"))
    if event_type in _SUBSCRIPTION_EVENTS:
        return _stripe_id(obj.get("id"))
    return None


def _stripe_id(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        nested = value.get("id")
        if isinstance(nested, str) and nested:
            return nested
    return None


def _cancels_at_period_end(current: dict[str, object]) -> bool:
    if current.get("cancel_at_period_end") is True:
        return True
    cancel_at = current.get("cancel_at")
    return type(cancel_at) is int and cancel_at > 0
