import json
from typing import cast

from app.core.config import get_settings
from app.core.errors import AppError


def create_checkout_url(plan_code: str, interval: str, organization_id: str) -> str | None:
    settings = get_settings()
    if settings.billing_provider != "stripe":
        return None
    if not settings.stripe_secret_key or not settings.billing_public_url:
        raise AppError(503, "billing_provider_unavailable", "Billing provider is not configured")
    try:
        import stripe

        prices = json.loads(settings.stripe_price_ids or "{}")
        price_id = prices.get(f"{plan_code}:{interval}")
        if not price_id:
            raise AppError(503, "billing_price_unavailable", "That billing price is not configured")
        stripe.api_key = settings.stripe_secret_key
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{settings.billing_public_url}/settings?billing=success",
            cancel_url=f"{settings.billing_public_url}/settings?billing=canceled",
            client_reference_id=organization_id,
        )
        return cast(str, session.url)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            502, "billing_provider_error", "The billing provider could not create checkout"
        ) from exc
