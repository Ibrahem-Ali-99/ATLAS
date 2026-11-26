import json
from typing import Any

import stripe

from app.core.config import get_settings
from app.core.errors import AppError


def price_map() -> dict[str, str]:
    try:
        raw = json.loads(get_settings().stripe_price_ids or "{}")
    except (ValueError, TypeError) as exc:
        raise AppError(
            503, "billing_price_unavailable", "Billing prices are not configured"
        ) from exc
    if not isinstance(raw, dict):
        raise AppError(503, "billing_price_unavailable", "Billing prices are not configured")
    return {key: value for key, value in raw.items() if isinstance(value, str) and value}


def _client() -> stripe.StripeClient:
    settings = get_settings()
    if (
        settings.billing_provider != "stripe"
        or not settings.stripe_secret_key.startswith(("sk_test_", "rk_test_"))
        or not settings.billing_public_url
        or not settings.stripe_webhook_secret
    ):
        raise AppError(
            503,
            "billing_provider_unavailable",
            "Stripe test-mode billing is not configured",
        )
    return stripe.StripeClient(
        settings.stripe_secret_key,
        http_client=stripe.RequestsClient(timeout=10),
        max_network_retries=1,
    )


def ensure_customer(organization_id: str) -> str:
    try:
        customer = _client().v1.customers.create(
            {"metadata": {"atlas_organization": organization_id}},
            options={"idempotency_key": f"atlas-billing-customer-{organization_id}"},
        )
    except stripe.StripeError as exc:
        raise AppError(
            502, "billing_provider_error", "Could not create the billing customer"
        ) from exc
    return customer.id


def create_checkout_url(
    plan_code: str, interval: str, organization_id: str, customer_id: str
) -> str:
    selection = f"{plan_code}:{interval}"
    price = price_map().get(selection)
    if not price or plan_code == "free":
        raise AppError(422, "billing_price_unavailable", "Choose a configured paid plan")
    base_url = get_settings().billing_public_url.rstrip("/")
    client = _client().v1
    try:
        subscriptions = client.subscriptions.list(
            {"customer": customer_id, "status": "all", "limit": 100}
        )
        if any(
            item.status not in {"canceled", "incomplete_expired"} for item in subscriptions.data
        ):
            raise AppError(
                409, "subscription_already_exists", "Manage your subscription in the billing portal"
            )
        open_sessions = client.checkout.sessions.list(
            {"customer": customer_id, "status": "open", "limit": 1}
        )
        if open_sessions.data:
            current = open_sessions.data[0]
            metadata = current.to_dict().get("metadata")
            if isinstance(metadata, dict) and metadata.get("atlas_price") == price and current.url:
                return current.url
            raise AppError(
                409, "checkout_already_open", "Finish the open checkout or wait for it to expire"
            )
        session = client.checkout.sessions.create(
            {
                "mode": "subscription",
                "customer": customer_id,
                "line_items": [{"price": price, "quantity": 1}],
                "success_url": f"{base_url}/billing?checkout=success",
                "cancel_url": f"{base_url}/billing?checkout=canceled",
                "client_reference_id": organization_id,
                "metadata": {"atlas_price": price},
                "subscription_data": {"metadata": {"atlas_organization": organization_id}},
            }
        )
    except stripe.StripeError as exc:
        raise AppError(
            502, "billing_provider_error", "The billing provider could not create checkout"
        ) from exc
    if not session.url:
        raise AppError(
            502, "billing_provider_error", "The billing provider returned no checkout link"
        )
    return session.url


def create_portal_url(customer_id: str) -> str:
    try:
        session = _client().v1.billing_portal.sessions.create(
            {
                "customer": customer_id,
                "return_url": f"{get_settings().billing_public_url.rstrip('/')}/billing",
            }
        )
    except stripe.StripeError as exc:
        raise AppError(502, "billing_provider_error", "The billing portal is unavailable") from exc
    return session.url


def retrieve_subscription(subscription_id: str) -> dict[str, Any]:
    try:
        return _client().v1.subscriptions.retrieve(subscription_id).to_dict()
    except stripe.StripeError as exc:
        raise AppError(
            502, "billing_provider_error", "Could not verify the current subscription"
        ) from exc


def verified_event(body: bytes, signature: str) -> dict[str, Any]:
    secret = get_settings().stripe_webhook_secret
    if not secret or not signature:
        raise AppError(400, "invalid_webhook_signature", "Webhook signature is invalid")
    try:
        stripe.Webhook.construct_event(body, signature, secret)
        payload = json.loads(body)
    except (stripe.SignatureVerificationError, ValueError, AttributeError) as exc:
        raise AppError(400, "invalid_webhook_signature", "Webhook could not be verified") from exc
    if not isinstance(payload, dict) or payload.get("livemode") is not False:
        raise AppError(400, "invalid_webhook", "A Stripe test-mode event is required")
    return payload
