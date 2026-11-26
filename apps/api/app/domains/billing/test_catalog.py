"""The six Stripe test prices for Starter, Pro, and Business.

Free has no product. Amounts are US cents. A second run reuses a product or
price that already has the ATLAS lookup key and the same amount.
"""

from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError


@dataclass(frozen=True)
class TestPrice:
    plan_code: str
    plan_name: str
    interval: str
    stripe_interval: str
    unit_amount: int
    currency: str = "usd"

    @property
    def map_key(self) -> str:
        return f"{self.plan_code}:{self.interval}"

    @property
    def lookup_key(self) -> str:
        return f"atlas_{self.plan_code}_{self.interval}"


TEST_PRICES: tuple[TestPrice, ...] = (
    TestPrice("starter", "Starter", "monthly", "month", 1_900),
    TestPrice("starter", "Starter", "yearly", "year", 19_000),
    TestPrice("pro", "Pro", "monthly", "month", 4_900),
    TestPrice("pro", "Pro", "yearly", "year", 49_000),
    TestPrice("business", "Business", "monthly", "month", 9_900),
    TestPrice("business", "Business", "yearly", "year", 99_000),
)


def ensure_test_catalog(client: Any) -> dict[str, str]:
    products = {price.plan_code: _ensure_product(client, price) for price in TEST_PRICES}
    return {
        price.map_key: _ensure_price(client, price, products[price.plan_code])
        for price in TEST_PRICES
    }


def _ensure_product(client: Any, price: TestPrice) -> str:
    found = _find_product(client, price.plan_code)
    if found is not None:
        return found
    created = client.products.create(
        {
            "name": f"ATLAS {price.plan_name}",
            "metadata": {"atlas_plan": price.plan_code, "atlas_catalog": "test"},
        },
        {"idempotency_key": f"atlas-test-product-{price.plan_code}"},
    )
    product_id = _identifier(created)
    if product_id is None or getattr(created, "livemode", False) is not False:
        raise AppError(502, "billing_provider_error", "Stripe did not return a test-mode product")
    return product_id


def _ensure_price(client: Any, price: TestPrice, product_id: str) -> str:
    found = _find_price(client, price)
    if found is not None:
        return found
    created = client.prices.create(
        {
            "product": product_id,
            "currency": price.currency,
            "unit_amount": price.unit_amount,
            "lookup_key": price.lookup_key,
            "nickname": f"ATLAS {price.plan_name} {price.interval}",
            "metadata": {
                "atlas_plan": price.plan_code,
                "atlas_interval": price.interval,
                "atlas_catalog": "test",
            },
            "recurring": {"interval": price.stripe_interval, "interval_count": 1},
        },
        {"idempotency_key": f"atlas-test-price-{price.lookup_key}"},
    )
    price_id = _identifier(created)
    if price_id is None or not _price_matches(created, price, product_id):
        raise AppError(
            502, "billing_provider_error", "Stripe did not return the expected test price"
        )
    return price_id


def _find_product(client: Any, plan_code: str) -> str | None:
    starting_after: str | None = None
    for _ in range(5):
        params: dict[str, object] = {"limit": 100}
        if starting_after is not None:
            params["starting_after"] = starting_after
        page = client.products.list(params)
        rows = list(getattr(page, "data", []) or [])
        for row in rows:
            metadata = _metadata(row)
            if metadata.get("atlas_plan") != plan_code or metadata.get("atlas_catalog") != "test":
                continue
            if getattr(row, "livemode", False) is not False:
                raise AppError(
                    409, "billing_subscription_mismatch", "A live product matches this plan"
                )
            product_id = _identifier(row)
            if product_id is None:
                continue
            return product_id
        if not rows or not getattr(page, "has_more", False):
            return None
        last_id = _identifier(rows[-1])
        if last_id is None:
            return None
        starting_after = last_id
    raise AppError(409, "billing_price_unavailable", "Too many Stripe products to match safely")


def _find_price(client: Any, price: TestPrice) -> str | None:
    page = client.prices.list({"lookup_keys": [price.lookup_key], "limit": 1})
    rows = list(getattr(page, "data", []) or [])
    if not rows:
        return None
    row = rows[0]
    product = getattr(row, "product", None)
    product_id = product if isinstance(product, str) else _identifier(product)
    if product_id is None or not _price_matches(row, price, product_id):
        raise AppError(
            409,
            "billing_price_unavailable",
            "An existing Stripe price does not match the ATLAS test catalog",
        )
    price_id = _identifier(row)
    if price_id is None:
        raise AppError(
            502, "billing_provider_error", "Stripe did not return the expected test price"
        )
    return price_id


def _price_matches(row: Any, price: TestPrice, product_id: str) -> bool:
    recurring = getattr(row, "recurring", None)
    product = getattr(row, "product", None)
    current_product = product if isinstance(product, str) else _identifier(product)
    trial_days = getattr(recurring, "trial_period_days", None)
    return (
        getattr(row, "livemode", False) is False
        and getattr(row, "unit_amount", None) == price.unit_amount
        and getattr(row, "currency", None) == price.currency
        and getattr(row, "lookup_key", None) == price.lookup_key
        and current_product == product_id
        and getattr(recurring, "interval", None) == price.stripe_interval
        and getattr(recurring, "interval_count", None) == 1
        and not trial_days
    )


def _metadata(row: Any) -> dict[str, str]:
    metadata = getattr(row, "metadata", None)
    if metadata is None:
        return {}
    if hasattr(metadata, "to_dict"):
        raw = metadata.to_dict()
    elif isinstance(metadata, dict):
        raw = metadata
    else:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _identifier(row: Any) -> str | None:
    if row is None:
        return None
    value = row if isinstance(row, str) else getattr(row, "id", None)
    if isinstance(value, str) and value:
        return value
    return None
