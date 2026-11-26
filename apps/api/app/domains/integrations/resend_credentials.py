"""Keep Resend test evidence attached to the sending key that produced it."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret
from app.domains.integrations.models import IntegrationConfig

TEST_RECIPIENT_KEY = "resend_test_recipient"
TEST_EVIDENCE_KEYS = frozenset(
    {
        "resend_test_message_id",
        "resend_test_verified_at",
        "resend_test_recipient",
        "resend_test_confirmation",
        "resend_test_last_event",
    }
)
_USER_CREDENTIAL_KEYS = frozenset({"username", "password", "resend_api_key"})


def retain_test_recipient(
    current: Mapping[str, Any] | None, incoming: Mapping[str, Any]
) -> dict[str, Any]:
    retained = {key: value for key, value in incoming.items() if key != TEST_RECIPIENT_KEY}
    if isinstance(current, Mapping):
        approved = current.get(TEST_RECIPIENT_KEY)
        if isinstance(approved, str) and approved:
            retained[TEST_RECIPIENT_KEY] = approved
    return retained


def email_credentials_for_storage(
    existing: IntegrationConfig | None,
    credentials: str,
    *,
    merge: bool,
) -> str:
    incoming = _object(credentials)
    if merge:
        if incoming and not all(
            key in _USER_CREDENTIAL_KEYS and isinstance(value, str) and value
            for key, value in incoming.items()
        ):
            raise AppError(
                422, "invalid_credential_update", "Enter both SMTP username and password"
            )
        if ("username" in incoming) != ("password" in incoming):
            raise AppError(
                422, "invalid_credential_update", "Enter both SMTP username and password"
            )
    prior = _stored_credentials(existing)
    cleaned = {key: value for key, value in incoming.items() if key not in TEST_EVIDENCE_KEYS}
    if merge:
        retained = {key: value for key, value in prior.items() if key not in TEST_EVIDENCE_KEYS}
        cleaned = {**retained, **cleaned}
    old_key = prior.get("resend_api_key")
    new_key = cleaned.get("resend_api_key")
    if isinstance(old_key, str) and old_key and old_key == new_key:
        for key in TEST_EVIDENCE_KEYS:
            if key in prior:
                cleaned[key] = prior[key]
    return json.dumps(cleaned)


def _object(credentials: str) -> dict[str, Any]:
    try:
        loaded = json.loads(credentials)
    except (TypeError, ValueError) as exc:
        raise AppError(
            422, "invalid_credential_update", "Email credentials must be a JSON object"
        ) from exc
    if not isinstance(loaded, dict):
        raise AppError(422, "invalid_credential_update", "Email credentials must be a JSON object")
    return loaded


def _stored_credentials(existing: IntegrationConfig | None) -> dict[str, Any]:
    if existing is None or not existing.encrypted_credentials:
        return {}
    try:
        loaded = json.loads(open_integration_secret(existing.encrypted_credentials))
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
