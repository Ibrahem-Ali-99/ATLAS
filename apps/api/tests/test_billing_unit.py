import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import billing as billing_api
from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.billing import provider
from app.domains.billing.models import OrganizationSubscription, SubscriptionStatus
from app.domains.billing.service import (
    PLAN_DEFINITIONS,
    enforce_limit,
    entitlement_plan_code,
    get_subscription,
)
from app.domains.identity.models import MembershipRole
from app.domains.observability.models import OperationTrace
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_all_plans_define_enforced_entitlements() -> None:
    required = {"seats", "ai_requests", "knowledge_storage_bytes", "active_workflows"}
    assert set(PLAN_DEFINITIONS) == {"free", "starter", "pro", "business"}
    for plan in PLAN_DEFINITIONS.values():
        assert required <= set(plan)
        assert all(isinstance(plan[key], int) and plan[key] > 0 for key in required)


def test_plan_limits_increase_with_tier() -> None:
    for key in ("seats", "ai_requests", "knowledge_storage_bytes", "active_workflows"):
        values = [PLAN_DEFINITIONS[name][key] for name in ("free", "starter", "pro", "business")]
        assert values == sorted(values)


def test_stripe_checkout_does_not_change_entitlements(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org = make_organization(db, "Billing workspace", "billing-workspace")
    admin = make_user(db, "billing-admin@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/billing"
    current = client.get(path).json()["subscription"]
    monkeypatch.setattr(get_settings(), "billing_provider", "stripe")
    monkeypatch.setattr(billing_api, "ensure_customer", lambda _: "cus_test_atlas")

    def checkout_url(*_args: str) -> str:
        bound_customer = db.scalar(
            select(OrganizationSubscription.provider_customer_id).where(
                OrganizationSubscription.organization_id == org.id
            )
        )
        assert bound_customer == "cus_test_atlas"
        return "https://checkout.example.test"

    monkeypatch.setattr(billing_api, "create_checkout_url", checkout_url)

    checkout = client.post(f"{path}/checkout", json={"plan_code": "pro"}, headers=headers)
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["status"] == "pending"
    row = db.scalar(
        select(OrganizationSubscription).where(OrganizationSubscription.organization_id == org.id)
    )
    assert row is not None
    assert row.plan_code == "free"
    assert client.get(path).json()["subscription"] == current
    assert client.post(f"{path}/portal", headers=headers).status_code == 503


def test_signed_checkout_reconciles_once_from_the_provider(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org = make_organization(db, "Stripe test workspace", "stripe-test-workspace")
    admin = make_user(db, "stripe-admin@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/billing"
    settings = get_settings()
    secret = "whsec_disposable_contract_fixture"
    monkeypatch.setattr(settings, "billing_provider", "stripe")
    monkeypatch.setattr(settings, "stripe_webhook_secret", secret)
    monkeypatch.setattr(settings, "stripe_price_ids", '{"pro:monthly":"price_pro"}')
    monkeypatch.setattr(billing_api, "ensure_customer", lambda _: "cus_atlas")
    monkeypatch.setattr(
        billing_api, "create_checkout_url", lambda *_: "https://checkout.example.test"
    )
    monkeypatch.setattr(billing_api, "create_portal_url", lambda _: "https://portal.example.test")
    subscription = {
        "customer": "cus_atlas",
        "livemode": False,
        "status": "active",
        "metadata": {"atlas_organization": str(org.id)},
        "items": {
            "data": [
                {
                    "price": {"id": "price_pro"},
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                }
            ]
        },
    }
    provider_calls: list[str] = []

    def retrieve(subscription_id: str) -> dict:
        provider_calls.append(subscription_id)
        return subscription

    monkeypatch.setattr(provider, "retrieve_subscription", retrieve)
    assert (
        client.post(f"{path}/checkout", json={"plan_code": "pro"}, headers=headers).status_code
        == 200
    )
    event = {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "livemode": False,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test",
                "customer": "cus_atlas",
                "subscription": "sub_atlas",
                "payment_status": "paid",
                "client_reference_id": str(org.id),
            }
        },
    }
    endpoint = "/api/v1/billing/webhooks/stripe"

    def deliver(payload: dict) -> int:
        body = json.dumps(payload).encode()
        stamp = int(time.time())
        signature = hmac.new(
            secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        return client.post(
            endpoint, content=body, headers={"Stripe-Signature": f"t={stamp},v1={signature}"}
        ).status_code

    assert client.post(endpoint, json=event).status_code == 400
    assert deliver(event) == 200
    assert deliver(event) == 200
    assert deliver({**event, "type": "customer.subscription.updated"}) == 409
    assert provider_calls == ["sub_atlas"]
    assert client.get(path).json()["subscription"]["plan_code"] == "pro"
    assert (
        client.post(f"{path}/portal", headers=headers).json()["portal_url"]
        == "https://portal.example.test"
    )


def _sign(secret: str, body: bytes, stamp: int | None = None) -> dict[str, str]:
    issued = int(time.time()) if stamp is None else stamp
    signature = hmac.new(secret.encode(), f"{issued}.".encode() + body, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={issued},v1={signature}"}


def _stripe_subscription(
    org_id: object,
    *,
    price: str = "price_pro",
    status: str = "active",
    start: int | None = None,
    end: int | None = None,
    cancel: bool = False,
    subscription_id: str = "sub_atlas",
    customer: str = "cus_atlas",
) -> dict[str, object]:
    now = int(time.time())
    period_start = now - 86_400 if start is None else start
    period_end = now + 30 * 86_400 if end is None else end
    current: dict[str, object] = {
        "id": subscription_id,
        "customer": customer,
        "livemode": False,
        "status": status,
        "metadata": {"atlas_organization": str(org_id)},
        "items": {
            "data": [
                {
                    "price": {"id": price},
                    "current_period_start": period_start,
                    "current_period_end": period_end,
                }
            ]
        },
    }
    if cancel:
        current["cancel_at_period_end"] = True
    return current


def _bind_stripe(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch, slug: str
) -> tuple[object, dict[str, str], str, dict[str, dict[str, object]]]:
    org = make_organization(db, slug, slug)
    admin = make_user(db, f"{slug}@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/billing"
    secret = "whsec_disposable_contract_fixture"
    settings = get_settings()
    monkeypatch.setattr(settings, "billing_provider", "stripe")
    monkeypatch.setattr(settings, "stripe_webhook_secret", secret)
    monkeypatch.setattr(
        settings,
        "stripe_price_ids",
        '{"starter:monthly":"price_starter","pro:monthly":"price_pro",'
        '"pro:yearly":"price_pro_year","business:monthly":"price_business"}',
    )
    monkeypatch.setattr(billing_api, "ensure_customer", lambda _: "cus_atlas")
    monkeypatch.setattr(
        billing_api, "create_checkout_url", lambda *_: "https://checkout.example.test"
    )
    state = {"subscription": _stripe_subscription(org.id)}

    def retrieve(subscription_id: str) -> dict[str, object]:
        assert subscription_id == state["subscription"]["id"]
        return state["subscription"]

    monkeypatch.setattr(provider, "retrieve_subscription", retrieve)
    checkout = client.post(f"{path}/checkout", json={"plan_code": "pro"}, headers=headers)
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["status"] == "pending"
    return org, headers, path, state


def _deliver(
    client: TestClient,
    secret: str,
    event_type: str,
    obj: dict[str, object],
    *,
    event_id: str | None = None,
    stamp: int | None = None,
    livemode: bool = False,
) -> object:
    payload = {
        "id": event_id or f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "livemode": livemode,
        "type": event_type,
        "data": {"object": obj},
    }
    body = json.dumps(payload).encode()
    return client.post(
        "/api/v1/billing/webhooks/stripe",
        content=body,
        headers=_sign(secret, body, stamp),
    )


def test_sandbox_plan_change_applies_immediately(client: TestClient, db: Session) -> None:
    org = make_organization(db, "Sandbox billing", "sandbox-billing")
    admin = make_user(db, "sandbox-billing@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/billing"
    changed = client.post(
        f"{path}/checkout",
        json={"plan_code": "starter", "billing_interval": "yearly"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["mode"] == "sandbox"
    body = client.get(path).json()
    assert body["subscription"]["plan_code"] == "starter"
    assert body["subscription"]["billing_interval"] == "yearly"
    assert body["subscription"]["entitled_plan_code"] == "starter"
    assert body["attention"] is None
    assert body["checkout_available"] is True
    assert body["portal_available"] is False
    repeat = client.post(
        f"{path}/checkout",
        json={"plan_code": "starter", "billing_interval": "yearly"},
        headers=headers,
    )
    assert repeat.status_code == 200, repeat.text
    assert client.get(path).json()["subscription"]["plan_code"] == "starter"


def test_staff_cannot_change_billing(client: TestClient, db: Session) -> None:
    org = make_organization(db, "Staff billing", "staff-billing")
    staff = make_user(db, "staff-billing@example.com")
    make_membership(db, staff, org, MembershipRole.staff)
    headers = _csrf(login(client, staff.email, PASSWORD))
    denied = client.post(
        f"/api/v1/organizations/{org.id}/billing/checkout",
        json={"plan_code": "starter"},
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"


def test_stripe_checkout_without_keys_does_not_grant_a_plan(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org = make_organization(db, "Unconfigured stripe", "unconfigured-stripe")
    admin = make_user(db, "unconfigured-stripe@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/billing"
    monkeypatch.setattr(get_settings(), "billing_provider", "stripe")
    checkout = client.post(f"{path}/checkout", json={"plan_code": "pro"}, headers=headers)
    assert checkout.status_code == 503
    assert checkout.json()["error"]["code"] == "billing_provider_unavailable"
    assert client.get(path).json()["subscription"]["plan_code"] == "free"


def test_stripe_webhook_is_rejected_until_billing_uses_stripe(client: TestClient) -> None:
    denied = client.post("/api/v1/billing/webhooks/stripe", content=b"{}")
    assert denied.status_code == 503
    assert denied.json()["error"]["code"] == "billing_provider_unavailable"


def test_unpaid_checkout_and_incomplete_subscription_do_not_grant_entitlements(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, headers, path, state = _bind_stripe(client, db, monkeypatch, "unpaid-checkout")
    secret = "whsec_disposable_contract_fixture"
    calls: list[str] = []

    def retrieve(subscription_id: str) -> dict[str, object]:
        calls.append(subscription_id)
        return state["subscription"]

    monkeypatch.setattr(provider, "retrieve_subscription", retrieve)
    unpaid = _deliver(
        client,
        secret,
        "checkout.session.completed",
        {
            "customer": "cus_atlas",
            "subscription": "sub_atlas",
            "payment_status": "unpaid",
            "client_reference_id": str(org.id),
        },
    )
    assert unpaid.status_code == 200, unpaid.text
    assert calls == []
    assert client.get(path).json()["subscription"]["plan_code"] == "free"

    state["subscription"] = _stripe_subscription(org.id, status="incomplete")
    incomplete = _deliver(
        client,
        secret,
        "checkout.session.completed",
        {
            "customer": "cus_atlas",
            "subscription": "sub_atlas",
            "payment_status": "paid",
            "client_reference_id": str(org.id),
        },
    )
    assert incomplete.status_code == 200, incomplete.text
    body = client.get(path).json()
    assert body["subscription"]["plan_code"] == "free"
    assert body["subscription"]["provider"] == "sandbox"
    assert body["plan"]["seats"] == PLAN_DEFINITIONS["free"]["seats"]

    mismatched = _deliver(
        client,
        secret,
        "checkout.session.async_payment_succeeded",
        {
            "customer": "cus_atlas",
            "subscription": "sub_atlas",
            "payment_status": "paid",
            "client_reference_id": str(uuid.uuid4()),
        },
    )
    assert mismatched.status_code == 200, mismatched.text
    assert client.get(path).json()["subscription"]["plan_code"] == "free"

    state["subscription"] = _stripe_subscription(org.id)
    confirmed = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_body = client.get(path).json()
    assert confirmed_body["subscription"]["plan_code"] == "pro"
    assert confirmed_body["subscription"]["entitled_plan_code"] == "pro"
    assert confirmed_body["subscription"]["provider"] == "stripe"
    assert confirmed_body["attention"] is None


def test_failed_payment_removes_paid_limits_until_stripe_confirms_recovery(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "failed-payment")
    secret = "whsec_disposable_contract_fixture"
    assert (
        _deliver(
            client,
            secret,
            "checkout.session.completed",
            {
                "customer": "cus_atlas",
                "subscription": "sub_atlas",
                "payment_status": "paid",
                "client_reference_id": str(org.id),
            },
        ).status_code
        == 200
    )
    state["subscription"] = _stripe_subscription(org.id, status="past_due")
    failed = _deliver(
        client,
        secret,
        "invoice.payment_failed",
        {
            "id": "in_failed",
            "customer": "cus_atlas",
            "parent": {"subscription_details": {"subscription": "sub_atlas"}},
        },
    )
    assert failed.status_code == 200, failed.text
    body = client.get(path).json()
    assert body["subscription"]["plan_code"] == "pro"
    assert body["subscription"]["entitled_plan_code"] == "free"
    assert body["subscription"]["status"] == "past_due"
    assert body["attention"] == "payment_failed"
    assert body["checkout_available"] is False
    assert body["portal_available"] is True
    assert body["plan"]["seats"] == PLAN_DEFINITIONS["free"]["seats"]

    recovered_start = int(time.time())
    state["subscription"] = _stripe_subscription(
        org.id, status="active", start=recovered_start, end=recovered_start + 30 * 86_400
    )
    recovered = _deliver(
        client,
        secret,
        "invoice.paid",
        {"id": "in_paid", "customer": "cus_atlas", "subscription": "sub_atlas"},
    )
    assert recovered.status_code == 200, recovered.text
    recovered_body = client.get(path).json()
    assert recovered_body["subscription"]["status"] == "active"
    assert recovered_body["subscription"]["entitled_plan_code"] == "pro"
    assert recovered_body["attention"] is None
    assert recovered_body["plan"]["seats"] == PLAN_DEFINITIONS["pro"]["seats"]


def test_renewal_starts_a_new_usage_period(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "renewal-period")
    secret = "whsec_disposable_contract_fixture"
    opened = int(time.time()) - 2 * 86_400
    state["subscription"] = _stripe_subscription(org.id, start=opened, end=opened + 10 * 86_400)
    paid = {
        "customer": "cus_atlas",
        "subscription": "sub_atlas",
        "payment_status": "paid",
        "client_reference_id": str(org.id),
    }
    assert _deliver(client, secret, "checkout.session.completed", paid).status_code == 200
    db.add(
        OperationTrace(
            organization_id=org.id,
            operation="assistant",
            status="accepted",
            started_at=datetime.fromtimestamp(opened + 3_600, UTC),
            attempt=1,
            langfuse_status="unconfigured",
            detail={},
        )
    )
    db.commit()
    assert client.get(path).json()["usage"]["ai_requests"] == 1
    renewed_at = int(time.time())
    state["subscription"] = _stripe_subscription(
        org.id, start=renewed_at, end=renewed_at + 30 * 86_400
    )
    renewed = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
    )
    assert renewed.status_code == 200, renewed.text
    body = client.get(path).json()
    assert body["subscription"]["plan_code"] == "pro"
    assert body["subscription"]["entitled_plan_code"] == "pro"
    assert body["usage"]["ai_requests"] == 0
    renewed_start = datetime.fromisoformat(body["subscription"]["current_period_start"])
    assert renewed_start == datetime.fromtimestamp(renewed_at, UTC)


def test_plan_changes_follow_the_current_stripe_price(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "plan-changes")
    secret = "whsec_disposable_contract_fixture"
    assert (
        _deliver(
            client,
            secret,
            "checkout.session.async_payment_succeeded",
            {
                "customer": "cus_atlas",
                "subscription": "sub_atlas",
                "payment_status": "paid",
                "client_reference_id": str(org.id),
            },
        ).status_code
        == 200
    )
    state["subscription"] = _stripe_subscription(org.id, price="price_business")
    upgraded = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
    )
    assert upgraded.status_code == 200, upgraded.text
    assert client.get(path).json()["subscription"]["plan_code"] == "business"
    assert client.get(path).json()["plan"]["seats"] == PLAN_DEFINITIONS["business"]["seats"]

    state["subscription"] = _stripe_subscription(org.id, price="price_starter")
    downgraded = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
    )
    assert downgraded.status_code == 200, downgraded.text
    downgraded_body = client.get(path).json()
    assert downgraded_body["subscription"]["plan_code"] == "starter"
    assert downgraded_body["subscription"]["entitled_plan_code"] == "starter"
    assert downgraded_body["plan"]["seats"] == PLAN_DEFINITIONS["starter"]["seats"]


def test_scheduled_cancellation_keeps_access_until_the_subscription_ends(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "scheduled-cancel")
    secret = "whsec_disposable_contract_fixture"
    assert (
        _deliver(
            client,
            secret,
            "checkout.session.completed",
            {
                "customer": "cus_atlas",
                "subscription": "sub_atlas",
                "payment_status": "paid",
                "client_reference_id": str(org.id),
            },
        ).status_code
        == 200
    )
    state["subscription"] = _stripe_subscription(org.id, cancel=True)
    scheduled = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
    )
    assert scheduled.status_code == 200, scheduled.text
    scheduled_body = client.get(path).json()
    assert scheduled_body["attention"] == "cancels_at_period_end"
    assert scheduled_body["subscription"]["cancels_at_period_end"] is True
    assert scheduled_body["subscription"]["entitled_plan_code"] == "pro"
    assert scheduled_body["checkout_available"] is False

    state["subscription"] = _stripe_subscription(org.id, status="canceled")
    ended = _deliver(
        client,
        secret,
        "customer.subscription.deleted",
        {"id": "sub_atlas", "customer": "cus_atlas"},
    )
    assert ended.status_code == 200, ended.text
    ended_body = client.get(path).json()
    assert ended_body["subscription"]["status"] == "canceled"
    assert ended_body["subscription"]["plan_code"] == "pro"
    assert ended_body["subscription"]["entitled_plan_code"] == "free"
    assert ended_body["attention"] == "canceled"
    assert ended_body["checkout_available"] is True
    assert ended_body["portal_available"] is True

    state["subscription"] = _stripe_subscription(
        org.id,
        price="price_pro_year",
        subscription_id="sub_replacement",
        end=int(time.time()) + 366 * 86_400,
    )
    replaced = _deliver(
        client,
        secret,
        "customer.subscription.created",
        {"id": "sub_replacement", "customer": "cus_atlas"},
    )
    assert replaced.status_code == 200, replaced.text
    replaced_body = client.get(path).json()
    assert replaced_body["subscription"]["plan_code"] == "pro"
    assert replaced_body["subscription"]["billing_interval"] == "yearly"
    assert replaced_body["subscription"]["entitled_plan_code"] == "pro"
    assert replaced_body["attention"] is None


def test_active_subscription_is_not_replaced_by_a_second_stripe_subscription(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "second-subscription")
    secret = "whsec_disposable_contract_fixture"
    assert (
        _deliver(
            client,
            secret,
            "checkout.session.completed",
            {
                "customer": "cus_atlas",
                "subscription": "sub_atlas",
                "payment_status": "paid",
                "client_reference_id": str(org.id),
            },
        ).status_code
        == 200
    )
    state["subscription"] = _stripe_subscription(
        org.id, price="price_business", subscription_id="sub_other"
    )
    ignored = _deliver(
        client,
        secret,
        "customer.subscription.created",
        {"id": "sub_other", "customer": "cus_atlas"},
    )
    assert ignored.status_code == 200, ignored.text
    body = client.get(path).json()
    assert body["subscription"]["plan_code"] == "pro"
    row = db.scalar(
        select(OrganizationSubscription).where(OrganizationSubscription.organization_id == org.id)
    )
    assert row is not None
    assert row.provider_subscription_id == "sub_atlas"


def test_webhook_failure_can_be_retried_and_stale_signatures_are_rejected(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "webhook-retry")
    secret = "whsec_disposable_contract_fixture"
    attempts = {"count": 0}

    def retrieve(subscription_id: str) -> dict[str, object]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise AppError(
                502, "billing_provider_error", "Could not verify the current subscription"
            )
        assert subscription_id == "sub_atlas"
        return state["subscription"]

    monkeypatch.setattr(provider, "retrieve_subscription", retrieve)
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "customer": "cus_atlas",
        "subscription": "sub_atlas",
        "payment_status": "paid",
        "client_reference_id": str(org.id),
    }
    failed = _deliver(client, secret, "checkout.session.completed", payload, event_id=event_id)
    assert failed.status_code == 502
    assert client.get(path).json()["subscription"]["plan_code"] == "free"
    retried = _deliver(client, secret, "checkout.session.completed", payload, event_id=event_id)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "accepted"
    assert client.get(path).json()["subscription"]["plan_code"] == "pro"
    duplicate = _deliver(client, secret, "checkout.session.completed", payload, event_id=event_id)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "already_processed"

    stale = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
        stamp=int(time.time()) - 3600,
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["code"] == "invalid_webhook_signature"
    live = _deliver(
        client,
        secret,
        "customer.subscription.updated",
        {"id": "sub_atlas", "customer": "cus_atlas"},
        livemode=True,
    )
    assert live.status_code == 400
    assert live.json()["error"]["code"] == "invalid_webhook"


def test_unmapped_price_does_not_consume_the_webhook(
    client: TestClient, db: Session, monkeypatch: MonkeyPatch
) -> None:
    org, _headers, path, state = _bind_stripe(client, db, monkeypatch, "unmapped-price")
    secret = "whsec_disposable_contract_fixture"
    state["subscription"] = _stripe_subscription(org.id, price="price_missing")
    event_id = f"evt_{uuid.uuid4().hex}"
    payload = {
        "customer": "cus_atlas",
        "subscription": "sub_atlas",
        "payment_status": "paid",
        "client_reference_id": str(org.id),
    }
    rejected = _deliver(client, secret, "checkout.session.completed", payload, event_id=event_id)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "billing_price_unavailable"
    assert client.get(path).json()["subscription"]["plan_code"] == "free"
    monkeypatch.setattr(
        get_settings(),
        "stripe_price_ids",
        '{"pro:monthly":"price_missing"}',
    )
    accepted = _deliver(client, secret, "checkout.session.completed", payload, event_id=event_id)
    assert accepted.status_code == 200, accepted.text
    assert client.get(path).json()["subscription"]["plan_code"] == "pro"


def test_paid_period_lapse_uses_free_limits_and_past_due_blocks_the_higher_plan(
    db: Session,
) -> None:
    org = make_organization(db, "Lapsed billing", "lapsed-billing")
    admin = make_user(db, "lapsed-billing@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    row = get_subscription(db, org.id)
    row.provider = "stripe"
    row.plan_code = "pro"
    row.status = SubscriptionStatus.active
    row.provider_customer_id = "cus_lapsed"
    row.provider_subscription_id = "sub_lapsed"
    row.current_period_end = datetime.now(UTC) - timedelta(hours=3)
    db.commit()
    assert entitlement_plan_code(row) == "free"
    with pytest.raises(AppError) as denied:
        enforce_limit(db, org.id, "seats", additional=2)
    assert denied.value.code == "entitlement_limit_reached"

    row.current_period_end = datetime.now(UTC) - timedelta(minutes=30)
    db.commit()
    assert entitlement_plan_code(row) == "pro"
    enforce_limit(db, org.id, "seats", additional=2)

    row.status = SubscriptionStatus.past_due
    row.current_period_end = datetime.now(UTC) + timedelta(days=10)
    db.commit()
    assert entitlement_plan_code(row) == "free"

    sandbox = get_subscription(db, make_organization(db, "Old sandbox", "old-sandbox").id)
    sandbox.plan_code = "pro"
    sandbox.status = SubscriptionStatus.active
    sandbox.provider = "sandbox"
    sandbox.current_period_end = datetime.now(UTC) - timedelta(days=90)
    assert entitlement_plan_code(sandbox) == "pro"
