from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.billing import provider


class _Record:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)

    def to_dict(self) -> dict[str, object]:
        metadata = self.__dict__.get("metadata")
        return {"metadata": metadata if isinstance(metadata, dict) else {}}


def _paid_price(
    *, amount: int = 2_000, interval: str = "month", trial_days: int | None = None
) -> _Record:
    return _Record(
        livemode=False,
        unit_amount=amount,
        recurring=_Record(interval=interval, interval_count=1, trial_period_days=trial_days),
    )


class _CheckoutApi:
    def __init__(self) -> None:
        self.price = _paid_price()
        self.subscriptions: list[_Record] = []
        self.open_sessions: list[_Record] = []
        self.created: list[dict[str, object]] = []

    def retrieve(self, price_id: str) -> _Record:
        assert price_id == "price_pro"
        return self.price

    def list_subscriptions(self, _params: dict[str, object]) -> _Record:
        return _Record(data=self.subscriptions)

    def list_sessions(self, _params: dict[str, object]) -> _Record:
        return _Record(data=self.open_sessions)

    def create_session(self, params: dict[str, object]) -> _Record:
        self.created.append(params)
        return _Record(url="https://checkout.stripe.test/c/session")


class _CheckoutClient:
    def __init__(self, api: _CheckoutApi) -> None:
        self.v1 = SimpleNamespace(
            prices=SimpleNamespace(retrieve=api.retrieve),
            subscriptions=SimpleNamespace(list=api.list_subscriptions),
            checkout=SimpleNamespace(
                sessions=SimpleNamespace(list=api.list_sessions, create=api.create_session)
            ),
        )


class _PortalApi:
    def __init__(self) -> None:
        self.products = {"price_starter": "prod_atlas", "price_pro": "prod_atlas"}
        self.configs: list[tuple[dict[str, object], dict[str, object] | None]] = []
        self.sessions: list[dict[str, object]] = []

    def retrieve(self, price_id: str) -> _Record:
        return _Record(product=self.products[price_id])

    def create_configuration(
        self, params: dict[str, object], options: dict[str, object] | None = None
    ) -> _Record:
        self.configs.append((params, options))
        return _Record(id="bpc_test")

    def create_session(self, params: dict[str, object]) -> _Record:
        self.sessions.append(params)
        return _Record(url="https://billing.stripe.test/p/session")


class _PortalClient:
    def __init__(self, api: _PortalApi) -> None:
        self.v1 = SimpleNamespace(
            prices=SimpleNamespace(retrieve=api.retrieve),
            billing_portal=SimpleNamespace(
                configurations=SimpleNamespace(create=api.create_configuration),
                sessions=SimpleNamespace(create=api.create_session),
            ),
        )


def _enable_stripe(monkeypatch: MonkeyPatch, prices: str) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "billing_provider", "stripe")
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_disposable")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_disposable")
    monkeypatch.setattr(settings, "billing_public_url", "http://127.0.0.1:3011")
    monkeypatch.setattr(settings, "stripe_price_ids", prices)
    provider._portal_configurations.clear()


def test_checkout_rejects_a_price_that_would_grant_access_without_payment(
    monkeypatch: MonkeyPatch,
) -> None:
    _enable_stripe(monkeypatch, '{"pro:monthly":"price_pro"}')
    api = _CheckoutApi()
    monkeypatch.setattr(provider, "_client", lambda: _CheckoutClient(api))
    api.price = _paid_price()
    api.price.livemode = True
    with pytest.raises(AppError) as live_price:
        provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert live_price.value.code == "billing_price_unavailable"
    api.price = _paid_price(amount=0)
    with pytest.raises(AppError) as zero:
        provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert zero.value.code == "billing_price_unavailable"
    api.price = _paid_price(trial_days=14)
    with pytest.raises(AppError) as trial:
        provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert trial.value.code == "billing_price_unavailable"
    api.price = _paid_price(interval="year")
    with pytest.raises(AppError) as interval:
        provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert interval.value.code == "billing_price_unavailable"
    assert api.created == []


def test_checkout_reuses_one_session_and_blocks_a_second_subscription(
    monkeypatch: MonkeyPatch,
) -> None:
    _enable_stripe(monkeypatch, '{"pro:monthly":"price_pro"}')
    api = _CheckoutApi()
    monkeypatch.setattr(provider, "_client", lambda: _CheckoutClient(api))
    api.subscriptions = [_Record(status="active")]
    with pytest.raises(AppError) as existing:
        provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert existing.value.code == "subscription_already_exists"

    api.subscriptions = [_Record(status="canceled")]
    api.open_sessions = [
        _Record(url="https://checkout.stripe.test/c/open", metadata={"atlas_price": "price_pro"})
    ]
    assert provider.create_checkout_url("pro", "monthly", "org_1", "cus_1") == (
        "https://checkout.stripe.test/c/open"
    )
    api.open_sessions = [
        _Record(url="https://checkout.stripe.test/c/other", metadata={"atlas_price": "price_other"})
    ]
    with pytest.raises(AppError) as open_checkout:
        provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert open_checkout.value.code == "checkout_already_open"

    api.open_sessions = []
    url = provider.create_checkout_url("pro", "monthly", "org_1", "cus_1")
    assert url == "https://checkout.stripe.test/c/session"
    created = api.created[0]
    assert created["payment_method_collection"] == "always"
    assert created["success_url"] == "http://127.0.0.1:3011/billing?checkout=success"
    assert created["cancel_url"] == "http://127.0.0.1:3011/billing?checkout=canceled"
    assert created["client_reference_id"] == "org_1"
    assert created["subscription_data"] == {"metadata": {"atlas_organization": "org_1"}}


def test_portal_configuration_schedules_downgrades_and_keeps_invoices(
    monkeypatch: MonkeyPatch,
) -> None:
    _enable_stripe(monkeypatch, '{"starter:monthly":"price_starter","pro:monthly":"price_pro"}')
    api = _PortalApi()
    monkeypatch.setattr(provider, "_client", lambda: _PortalClient(api))
    assert provider.create_portal_url("cus_1") == "https://billing.stripe.test/p/session"
    assert provider.create_portal_url("cus_1") == "https://billing.stripe.test/p/session"
    assert len(api.configs) == 1
    params, options = api.configs[0]
    features = params["features"]
    assert isinstance(features, dict)
    assert features["invoice_history"] == {"enabled": True}
    assert features["payment_method_update"] == {"enabled": True}
    assert features["subscription_pause"] == {"enabled": False}
    assert features["subscription_cancel"]["mode"] == "at_period_end"
    update = features["subscription_update"]
    assert update["proration_behavior"] == "always_invoice"
    assert update["default_allowed_updates"] == ["price"]
    assert update["schedule_at_period_end"]["conditions"] == [
        {"type": "decreasing_item_amount"},
        {"type": "shortening_interval"},
    ]
    assert update["products"] == [
        {"product": "prod_atlas", "prices": ["price_pro", "price_starter"]}
    ]
    assert options is not None
    assert str(options["idempotency_key"]).startswith("atlas-portal-")
    assert api.sessions[0]["configuration"] == "bpc_test"
    assert api.sessions[0]["return_url"] == "http://127.0.0.1:3011/billing?portal=return"
    assert api.sessions[1]["configuration"] == "bpc_test"


def test_portal_features_stop_at_the_stripe_product_limit() -> None:
    prices = {f"price_{index}": f"prod_{index}" for index in range(11)}
    with pytest.raises(AppError) as exceeded:
        provider.portal_features(prices)
    assert exceeded.value.code == "billing_price_unavailable"
    without_prices = provider.portal_features({})
    assert "subscription_update" not in without_prices
    assert without_prices["invoice_history"]["enabled"] is True


def test_live_secret_cannot_open_the_billing_portal(monkeypatch: MonkeyPatch) -> None:
    _enable_stripe(monkeypatch, "{}")
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_live_disposable")
    with pytest.raises(AppError) as denied:
        provider.create_portal_url("cus_1")
    assert denied.value.code == "billing_provider_unavailable"


def test_restricted_test_key_is_accepted(monkeypatch: MonkeyPatch) -> None:
    _enable_stripe(monkeypatch, "{}")
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "rk_test_disposable")
    seen: dict[str, str] = {}

    def client(key: str, **_kwargs: object) -> str:
        seen["key"] = key
        return key

    monkeypatch.setattr(provider.stripe, "StripeClient", client)
    assert provider._client() == "rk_test_disposable"
    assert seen["key"] == "rk_test_disposable"
