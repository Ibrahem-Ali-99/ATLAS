import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.integrations.email_delivery_policy import live_delivery_eligibility


class ScalarSequence:
    def __init__(self, *values: object) -> None:
        self.values = list(values)

    def scalar(self, _statement: object) -> object:
        return self.values.pop(0)


def eligible_config(**updates: object) -> SimpleNamespace:
    config = {
        "live_delivery_enabled": True,
        "sender_domain_verified": True,
        "sender_domain_verification_method": "dns",
        "allowed_recipient_domains": ["harbor.example"],
    }
    config.update(updates)
    return SimpleNamespace(
        status="configured",
        encrypted_credentials="encrypted",
        verified_at=datetime.now(UTC),
        config=config,
    )


def intent(contact_id: uuid.UUID, recipient: str = "mina@harbor.example") -> SimpleNamespace:
    return SimpleNamespace(
        organization_id=uuid.uuid4(),
        payload={
            "to": recipient,
            "contact_id": str(contact_id),
            "recipient_snapshot": recipient,
        },
    )


def test_live_delivery_requires_all_gates() -> None:
    contact_id = uuid.uuid4()
    approval_intent = intent(contact_id)
    db = ScalarSequence(
        eligible_config(),
        SimpleNamespace(
            organization_id=approval_intent.organization_id,
            email="mina@harbor.example",
        ),
    )

    result = live_delivery_eligibility(db, approval_intent)

    assert result.eligible


def test_live_delivery_requires_domain_evidence() -> None:
    contact_id = uuid.uuid4()
    approval_intent = intent(contact_id)
    db = ScalarSequence(
        eligible_config(sender_domain_verified=False),
        SimpleNamespace(email="mina@harbor.example"),
    )

    result = live_delivery_eligibility(db, approval_intent)

    assert result.reason == "sender_domain_not_verified"


def test_live_delivery_rejects_changed_recipient() -> None:
    contact_id = uuid.uuid4()
    approval_intent = intent(contact_id)
    db = ScalarSequence(eligible_config(), SimpleNamespace(email="other@harbor.example"))

    result = live_delivery_eligibility(db, approval_intent)

    assert result.reason == "recipient_changed"


def test_live_delivery_rejects_disallowed_domain() -> None:
    contact_id = uuid.uuid4()
    approval_intent = intent(contact_id, "mina@outside.example")
    db = ScalarSequence(
        eligible_config(),
        SimpleNamespace(email="mina@outside.example"),
    )

    result = live_delivery_eligibility(db, approval_intent)

    assert result.reason == "recipient_domain_disallowed"


def test_live_delivery_rejects_disabled_configuration() -> None:
    contact_id = uuid.uuid4()
    approval_intent = intent(contact_id)
    db = ScalarSequence(
        SimpleNamespace(
            status="disabled",
            encrypted_credentials="encrypted",
            verified_at=datetime.now(UTC),
            config={},
        ),
        SimpleNamespace(email="mina@harbor.example"),
    )

    result = live_delivery_eligibility(db, approval_intent)

    assert result.reason == "email_integration_disabled"
