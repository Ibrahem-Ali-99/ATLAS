import uuid
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.integrations import email


def test_recipient_normalization_accepts_mailpit_and_rejects_ambiguous_values() -> None:
    assert email.normalize_recipient(" Customer@localhost ") == "customer@localhost"
    assert email.normalize_recipient("Customer <customer@example.com>") == "customer@example.com"
    with pytest.raises(AppError) as exc:
        email.normalize_recipient("not-an-address")
    assert exc.value.code == "invalid_recipient"


def test_disabled_organization_email_override_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        email,
        "read_metadata",
        lambda _db, _organization_id, _integration_type: SimpleNamespace(
            status=email.IntegrationStatus.disabled,
            provider="smtp",
            config={"host": "mailpit", "port": 1025},
        ),
    )
    with pytest.raises(AppError) as exc:
        email.send_email(
            email.OutboundEmail("customer@localhost", "Subject", "Body", "intent-1"),
            db=object(),
            organization_id=uuid.uuid4(),
        )
    assert exc.value.code == "email_integration_disabled"


def test_configured_org_smtp_never_replaces_mailpit_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        email,
        "read_metadata",
        lambda _db, _organization_id, _integration_type: SimpleNamespace(
            status=email.IntegrationStatus.configured,
            provider="smtp",
            config={"host": "smtp.external.invalid", "port": 587},
        ),
    )
    monkeypatch.setattr(
        email,
        "get_settings",
        lambda: SimpleNamespace(
            email_mode="sandbox",
            email_live_enabled=False,
            smtp_host="mailpit",
            smtp_port=1025,
            smtp_timeout_seconds=1,
            smtp_from="ATLAS <noreply@localhost>",
        ),
    )
    seen: list[tuple[str, int]] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            seen.append((host, port))

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send_message(self, _message: object) -> None:
            return None

    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    receipt = email.send_email(
        email.OutboundEmail("customer@localhost", "Subject", "Body", "intent-1"),
        db=object(),
        organization_id=uuid.uuid4(),
    )
    assert receipt.mode == "sandbox"
    assert seen == [("mailpit", 1025)]
