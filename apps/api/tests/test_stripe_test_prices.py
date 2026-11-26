from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.domains.billing.test_catalog import TEST_PRICES, ensure_test_catalog
from app.scripts.stripe_test_prices import billing_environment, write_billing_env


class _Page:
    def __init__(self, data: list[object], has_more: bool = False) -> None:
        self.data = data
        self.has_more = has_more


class _Catalog:
    def __init__(self) -> None:
        self.products_listed = 0
        self.created_products: list[dict[str, object]] = []
        self.created_prices: list[dict[str, object]] = []
        self.products = self
        self.prices = self
        self._products: list[SimpleNamespace] = []
        self._prices: list[SimpleNamespace] = []

    def list(self, params: dict[str, object]) -> _Page:
        if "lookup_keys" in params:
            keys = params["lookup_keys"]
            return _Page([row for row in self._prices if row.lookup_key in keys])
        self.products_listed += 1
        return _Page(self._products)

    def create(
        self, params: dict[str, object], options: dict[str, str] | None = None
    ) -> SimpleNamespace:
        if "unit_amount" in params:
            self.created_prices.append(params)
            row = SimpleNamespace(
                id=f"price_{params['lookup_key']}",
                livemode=False,
                unit_amount=params["unit_amount"],
                currency=params["currency"],
                lookup_key=params["lookup_key"],
                product=params["product"],
                recurring=SimpleNamespace(
                    interval=params["recurring"]["interval"],
                    interval_count=params["recurring"]["interval_count"],
                    trial_period_days=None,
                ),
            )
            self._prices.append(row)
            return row
        self.created_products.append({"params": params, "options": options})
        row = SimpleNamespace(
            id=f"prod_{params['metadata']['atlas_plan']}",
            livemode=False,
            metadata=params["metadata"],
        )
        self._products.append(row)
        return row


def test_catalog_is_the_six_usd_prices() -> None:
    assert [(price.map_key, price.unit_amount, price.currency) for price in TEST_PRICES] == [
        ("starter:monthly", 1_900, "usd"),
        ("starter:yearly", 19_000, "usd"),
        ("pro:monthly", 4_900, "usd"),
        ("pro:yearly", 49_000, "usd"),
        ("business:monthly", 9_900, "usd"),
        ("business:yearly", 99_000, "usd"),
    ]
    assert "free" not in {price.plan_code for price in TEST_PRICES}


def test_catalog_creation_is_reused(tmp_path) -> None:
    catalog = _Catalog()
    first = ensure_test_catalog(catalog)
    second = ensure_test_catalog(catalog)
    assert first == second
    assert set(first) == {price.map_key for price in TEST_PRICES}
    assert len(catalog.created_products) == 3
    assert len(catalog.created_prices) == 6
    assert catalog.created_products[0]["options"] == {
        "idempotency_key": "atlas-test-product-starter"
    }

    env = tmp_path / ".env"
    env.write_text(
        "ATLAS_WHATSAPP_LIVE_ENABLED=false\n"
        "ATLAS_LLM_API_KEY=keep-me\n"
        "ATLAS_STRIPE_WEBHOOK_SECRET=whsec_keep\n",
        encoding="utf-8",
    )
    updates = billing_environment("sk_test_example", first, "http://127.0.0.1:3000", "")
    del updates["ATLAS_STRIPE_WEBHOOK_SECRET"]
    write_billing_env(env, updates)
    write_billing_env(env, updates)
    text = env.read_text(encoding="utf-8")
    assert "ATLAS_WHATSAPP_LIVE_ENABLED=false" in text
    assert "ATLAS_LLM_API_KEY=keep-me" in text
    assert "ATLAS_STRIPE_WEBHOOK_SECRET=whsec_keep" in text
    assert "ATLAS_BILLING_PROVIDER=stripe" in text
    assert text.count("ATLAS_STRIPE_SECRET_KEY=") == 1
    assert "ATLAS_STRIPE_SECRET_KEY=sk_test_example" in text
    assert "starter:monthly" in text
    assert text.index("ATLAS_WHATSAPP_LIVE_ENABLED") < text.index("ATLAS_BILLING_PROVIDER")


def test_existing_price_with_a_different_amount_is_not_replaced() -> None:
    catalog = _Catalog()
    ensure_test_catalog(catalog)
    catalog._prices[0].unit_amount = 100
    with pytest.raises(AppError) as rejected:
        ensure_test_catalog(catalog)
    assert rejected.value.code == "billing_price_unavailable"
