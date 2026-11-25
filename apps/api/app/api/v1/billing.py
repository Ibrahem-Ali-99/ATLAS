import hashlib
import hmac
import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.billing.models import BillingWebhookEvent, SubscriptionPlan
from app.domains.billing.provider import create_checkout_url
from app.domains.billing.service import (
    change_subscription,
    ensure_plans,
    get_subscription,
    plan_for,
    reconcile_provider_event,
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
    plan = plan_for(db, row.plan_code)
    db.commit()
    return {
        "subscription": {
            "plan_code": row.plan_code,
            "billing_interval": row.billing_interval,
            "status": row.status.value,
            "provider": row.provider,
            "current_period_start": row.current_period_start,
            "current_period_end": row.current_period_end,
        },
        "plan": plan.entitlements,
        "usage": usage(db, member.organization.id),
    }


@router.post("/organizations/{organization_id}/billing/checkout")
def checkout(body: CheckoutBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    provider_url = create_checkout_url(
        body.plan_code, body.billing_interval, str(admin.organization.id)
    )
    row = change_subscription(
        db, admin.organization.id, admin.user.id, body.plan_code, body.billing_interval
    )
    return {
        "mode": get_settings().billing_provider,
        "checkout_url": provider_url or f"/settings?billing=updated&plan={row.plan_code}",
        "status": row.status.value,
    }


@router.post("/organizations/{organization_id}/billing/portal")
def portal(admin: CsrfAdmin) -> dict[str, str]:
    return {"portal_url": "/settings?billing=manage"}


@router.post("/billing/webhooks/stripe")
async def stripe_webhook(request: Request, db: DbSession) -> dict[str, str]:
    body = await request.body()
    secret = get_settings().stripe_webhook_secret
    supplied = request.headers.get("x-atlas-webhook-signature", "")
    if not secret or not hmac.compare_digest(
        supplied, hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    ):
        raise AppError(400, "invalid_webhook_signature", "Webhook signature is invalid")
    payload = json.loads(body)
    event_id = str(payload.get("id", ""))
    if not event_id:
        raise AppError(400, "invalid_webhook", "Webhook event id is required")
    if (
        db.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == event_id))
        is not None
    ):
        return {"status": "already_processed", "event_id": event_id}
    db.add(
        BillingWebhookEvent(
            provider="stripe", event_id=event_id, payload_hash=hashlib.sha256(body).hexdigest()
        )
    )
    reconcile_provider_event(db, payload)
    db.commit()
    return {"status": "accepted", "event_id": event_id}
