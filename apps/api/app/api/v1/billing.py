import hashlib

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.billing.models import BillingWebhookEvent, SubscriptionPlan, SubscriptionStatus
from app.domains.billing.provider import (
    create_checkout_url,
    create_portal_url,
    ensure_customer,
    verified_event,
)
from app.domains.billing.service import (
    billing_attention,
    change_subscription,
    checkout_available,
    ensure_plans,
    entitlement_plan_code,
    get_subscription,
    plan_for,
    reconcile_provider_event,
    scheduled_cancellation,
    usage,
)
from app.domains.identity.dependencies import CsrfAdmin, DbSession, Member

router = APIRouter(tags=["billing"])


class CheckoutBody(BaseModel):
    plan_code: str = Field(pattern=r"^(free|starter|pro|business)$")
    billing_interval: str = Field(default="monthly", pattern=r"^(monthly|yearly)$")


@router.get("/organizations/{organization_id}/billing/plans")
def plans(member: Member, db: DbSession) -> list[dict[str, object]]:
    ensure_plans(db)
    db.commit()
    return [
        {"code": p.code, "name": p.name, "entitlements": p.entitlements}
        for p in db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.active.is_(True))).all()
    ]


@router.get("/organizations/{organization_id}/billing")
def status(member: Member, db: DbSession) -> dict[str, object]:
    row = get_subscription(db, member.organization.id)
    entitled = entitlement_plan_code(row)
    plan = plan_for(db, entitled)
    cancels = row.status in {
        SubscriptionStatus.active,
        SubscriptionStatus.trialing,
    } and scheduled_cancellation(db, row.organization_id)
    db.commit()
    return {
        "mode": get_settings().billing_provider,
        "portal_available": row.provider == "stripe" and bool(row.provider_customer_id),
        "checkout_available": checkout_available(row),
        "attention": billing_attention(row, cancels),
        "subscription": {
            "plan_code": row.plan_code,
            "entitled_plan_code": entitled,
            "billing_interval": row.billing_interval,
            "status": row.status.value,
            "provider": row.provider,
            "cancels_at_period_end": cancels,
            "current_period_start": row.current_period_start,
            "current_period_end": row.current_period_end,
        },
        "plan": plan.entitlements,
        "usage": usage(db, member.organization.id),
    }


@router.post("/organizations/{organization_id}/billing/checkout")
def checkout(body: CheckoutBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    if get_settings().billing_provider == "stripe":
        if body.plan_code == "free":
            raise AppError(422, "billing_price_unavailable", "Choose a paid plan for checkout")
        row = get_subscription(db, admin.organization.id, lock=True)
        plan_for(db, body.plan_code)
        customer_id = row.provider_customer_id
        if customer_id is None:
            customer_id = ensure_customer(str(admin.organization.id))
            row.provider_customer_id = customer_id
            # Webhook reconciliation must see the customer binding before checkout can start.
            db.commit()
            get_subscription(db, admin.organization.id, lock=True)
        provider_url = create_checkout_url(
            body.plan_code,
            body.billing_interval,
            str(admin.organization.id),
            customer_id,
        )
        db.commit()
        return {"mode": "stripe", "checkout_url": provider_url, "status": "pending"}
    row = change_subscription(
        db, admin.organization.id, admin.user.id, body.plan_code, body.billing_interval
    )
    return {
        "mode": "sandbox",
        "checkout_url": f"/settings?billing=updated&plan={row.plan_code}",
        "status": row.status.value,
    }


@router.post("/organizations/{organization_id}/billing/portal")
def portal(admin: CsrfAdmin, db: DbSession) -> dict[str, str]:
    row = get_subscription(db, admin.organization.id)
    if row.provider != "stripe" or not row.provider_customer_id:
        raise AppError(
            503, "billing_portal_unavailable", "A self-service billing portal is unavailable"
        )
    return {"portal_url": create_portal_url(row.provider_customer_id)}


@router.post("/billing/webhooks/stripe")
async def stripe_webhook(request: Request, db: DbSession) -> dict[str, str]:
    body = await request.body()
    return await run_in_threadpool(
        _accept_stripe_event, db, body, request.headers.get("stripe-signature", "")
    )


def _accept_stripe_event(db: DbSession, body: bytes, signature: str) -> dict[str, str]:
    if get_settings().billing_provider != "stripe":
        raise AppError(503, "billing_provider_unavailable", "Stripe billing is disabled")
    payload = verified_event(body, signature)
    event_id = payload.get("id")
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 200:
        raise AppError(400, "invalid_webhook", "Webhook event id is required")
    digest = hashlib.sha256(body).hexdigest()
    receipt = db.scalar(
        insert(BillingWebhookEvent)
        .values(provider="stripe", event_id=event_id, payload_hash=digest)
        .on_conflict_do_nothing(index_elements=[BillingWebhookEvent.event_id])
        .returning(BillingWebhookEvent.id)
    )
    if receipt is None:
        previous_hash = db.scalar(
            select(BillingWebhookEvent.payload_hash).where(BillingWebhookEvent.event_id == event_id)
        )
        if previous_hash != digest:
            raise AppError(
                409, "webhook_event_conflict", "Webhook event differs from its recorded receipt"
            )
        return {"status": "already_processed", "event_id": event_id}
    reconcile_provider_event(db, payload)
    db.commit()
    return {"status": "accepted", "event_id": event_id}
