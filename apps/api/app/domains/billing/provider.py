import hashlib
import json
from typing import Any

import stripe

from app.core.config import get_settings
from app.core.errors import AppError

_portal_configurations: dict[str, str] = {}


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
    _require_paid_price(client, price, interval)
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
                "payment_method_collection": "always",
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


def portal_features(price_products: dict[str, str]) -> dict[str, Any]:
    """Portal behavior for a confirmed Stripe customer.

    Upgrades invoice immediately, so the higher plan is stored only after Stripe
    confirms payment. Downgrades and shorter intervals wait until the paid period
    ends. Cancellation also waits until that period ends.
    """

    grouped: dict[str, list[str]] = {}
    for price_id, product_id in sorted(price_products.items()):
        if not price_id or not product_id:
            continue
        prices = grouped.setdefault(product_id, [])
        if price_id not in prices:
            prices.append(price_id)
    if len(grouped) > 10:
        raise AppError(
            422, "billing_price_unavailable", "The billing portal supports at most 10 products"
        )
    features: dict[str, Any] = {
        "customer_update": {
            "allowed_updates": ["email", "name", "address"],
            "enabled": True,
        },
        "invoice_history": {"enabled": True},
        "payment_method_update": {"enabled": True},
        "subscription_cancel": {
            "enabled": True,
            "mode": "at_period_end",
            "proration_behavior": "none",
        },
        "subscription_pause": {"enabled": False},
    }
    if grouped:
        features["subscription_update"] = {
            "enabled": True,
            "default_allowed_updates": ["price"],
            "proration_behavior": "always_invoice",
            "billing_cycle_anchor": "unchanged",
            "schedule_at_period_end": {
                "conditions": [
                    {"type": "decreasing_item_amount"},
                    {"type": "shortening_interval"},
                ]
            },
            "products": [
                {"product": product_id, "prices": prices}
                for product_id, prices in sorted(grouped.items())
            ],
        }
    return features


def create_portal_url(customer_id: str) -> str:
    root = _client()
    features = portal_features(_price_products(root.v1))
    configuration_id = _portal_configuration(root.v1, features)
    try:
        return_url = f"{get_settings().billing_public_url.rstrip('/')}/billing?portal=return"
        session = root.v1.billing_portal.sessions.create(
            {
                "customer": customer_id,
                "return_url": return_url,
                "configuration": configuration_id,
            }
        )
    except stripe.StripeError as exc:
        raise AppError(502, "billing_provider_error", "The billing portal is unavailable") from exc
    if not session.url:
        raise AppError(502, "billing_provider_error", "The billing portal is unavailable")
    return session.url


def _require_paid_price(client: Any, price_id: str, interval: str) -> None:
    try:
        price = client.prices.retrieve(price_id)
    except stripe.StripeError as exc:
        raise AppError(
            502, "billing_provider_error", "The billing provider could not create checkout"
        ) from exc
    if getattr(price, "livemode", None) is not False:
        raise AppError(422, "billing_price_unavailable", "Choose a Stripe test-mode price")
    amount = getattr(price, "unit_amount", None)
    recurring = getattr(price, "recurring", None)
    expected = "month" if interval == "monthly" else "year"
    trial_days = getattr(recurring, "trial_period_days", None)
    if (
        type(amount) is not int
        or amount <= 0
        or getattr(recurring, "interval", None) != expected
        or getattr(recurring, "interval_count", None) != 1
        or trial_days
    ):
        raise AppError(
            422,
            "billing_price_unavailable",
            "The Stripe price must be a recurring paid interval with no trial",
        )


def _price_products(client: Any) -> dict[str, str]:
    products: dict[str, str] = {}
    for price_id in price_map().values():
        try:
            price = client.prices.retrieve(price_id)
        except stripe.StripeError as exc:
            raise AppError(
                502, "billing_provider_error", "Could not prepare the billing portal"
            ) from exc
        product = getattr(price, "product", None)
        product_id = product if isinstance(product, str) else getattr(product, "id", None)
        if not isinstance(product_id, str) or not product_id:
            raise AppError(
                502, "billing_provider_error", "A billing price is not attached to a product"
            )
        products[price_id] = product_id
    return products


def _portal_configuration(client: Any, features: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(features, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    cached = _portal_configurations.get(digest)
    if cached:
        return cached
    try:
        created = client.billing_portal.configurations.create(
            {"features": features, "metadata": {"atlas_portal": digest}, "name": "ATLAS billing"},
            options={"idempotency_key": f"atlas-portal-{digest}"},
        )
    except stripe.StripeError as exc:
        raise AppError(502, "billing_provider_error", "The billing portal is unavailable") from exc
    configuration_id = getattr(created, "id", None)
    if not isinstance(configuration_id, str) or not configuration_id:
        raise AppError(502, "billing_provider_error", "The billing portal is unavailable")
    _portal_configurations[digest] = configuration_id
    return configuration_id


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
