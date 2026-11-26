import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import billing as billing_api
from app.core.config import get_settings
from app.domains.billing import provider
from app.domains.billing.models import OrganizationSubscription
from app.domains.billing.service import PLAN_DEFINITIONS
from app.domains.identity.models import MembershipRole
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
        "id": "evt_paid",
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
