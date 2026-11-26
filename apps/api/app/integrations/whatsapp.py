"""Official Meta WhatsApp Cloud API adapter.

The adapter is only invoked by the approved execution path. It never accepts
credentials from callers and refuses to send while ATLAS is in sandbox mode.
"""
# ruff: noqa: E501

import json
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.integrations.outcomes import OutcomeUncertain


def normalize_phone(value: str) -> str:
    normalized = re.sub(r"[ ()-]", "", value.strip()).removeprefix("+")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", normalized):
        raise AppError(422, "invalid_whatsapp_recipient", "Use a WhatsApp number with country code")
    return normalized


def parse_cloud_webhook(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Extract supported text messages and delivery statuses from Meta's envelope."""
    messages: list[dict[str, str]] = []
    statuses: list[dict[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_id = str(value.get("metadata", {}).get("phone_number_id", ""))
            for item in value.get("messages", []):
                if item.get("type") != "text" or not item.get("id"):
                    continue
                text = item.get("text", {}).get("body")
                sender = item.get("from")
                if isinstance(text, str) and isinstance(sender, str) and text.strip():
                    messages.append(
                        {
                            "id": str(item["id"]),
                            "sender": sender,
                            "body": text,
                            "phone_number_id": phone_id,
                        }
                    )
            for item in value.get("statuses", []):
                if item.get("id") and item.get("status"):
                    statuses.append(
                        {
                            "id": str(item["id"]),
                            "status": str(item["status"]),
                            "phone_number_id": phone_id,
                        }
                    )
    return messages, statuses


def send_whatsapp_text(
    db: Session,
    organization_id: uuid.UUID,
    recipient: str,
    body: str,
    *,
    template_name: str | None = None,
    template_language: str = "en_US",
    test_reply: bool = False,
) -> str:
    settings = get_settings()
    production = settings.email_mode == "live" and settings.whatsapp_live_enabled
    if test_reply:
        if production or settings.whatsapp_live_enabled:
            raise AppError(
                409,
                "whatsapp_test_reply_unavailable",
                "Restricted test replies stay off while customer messaging is enabled",
            )
        if isinstance(template_name, str) and template_name.strip():
            raise AppError(
                409,
                "whatsapp_template_unavailable",
                "A restricted test reply cannot use a WhatsApp template",
            )
    elif not production:
        raise AppError(
            409, "sandbox_delivery_only", "WhatsApp delivery is disabled in sandbox mode"
        )
    record = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
            IntegrationConfig.status == IntegrationStatus.configured,
            IntegrationConfig.verified_at.is_not(None),
        )
    )
    if record is None or not record.encrypted_credentials:
        raise AppError(503, "whatsapp_unconfigured", "Verify the workspace WhatsApp connection")
    try:
        credentials = json.loads(open_integration_secret(record.encrypted_credentials))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            503, "whatsapp_credentials_invalid", "WhatsApp credentials are invalid"
        ) from exc
    token = credentials.get("access_token") if isinstance(credentials, dict) else None
    phone_id = record.config.get("phone_number_id")
    if (
        not isinstance(token, str)
        or not token.strip()
        or not isinstance(phone_id, str)
        or not re.fullmatch(r"[0-9]{1,32}", phone_id)
    ):
        raise AppError(
            503, "whatsapp_configuration_incomplete", "WhatsApp configuration is incomplete"
        )
    recipient = normalize_phone(recipient)
    if test_reply:
        from app.domains.integrations.whatsapp_test import prepare_test_send

        prepare_test_send(db, organization_id, recipient, token, phone_id)
    if template_name:
        message: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {"name": template_name, "language": {"code": template_language}},
        }
    else:
        message = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
    try:
        response = httpx.post(
            f"https://graph.facebook.com/v21.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=message,
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        _release_test_reply(db, organization_id, test_reply, uncertain=True)
        raise OutcomeUncertain("whatsapp_transport_error") from exc
    if response.status_code >= 500 or response.status_code == 408:
        _release_test_reply(db, organization_id, test_reply, uncertain=True)
        raise OutcomeUncertain("whatsapp_provider_unavailable")
    if not response.is_success:
        _release_test_reply(db, organization_id, test_reply, uncertain=False)
        raise _provider_failure(response)
    try:
        message_id = response.json()["messages"][0]["id"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        _release_test_reply(db, organization_id, test_reply, uncertain=True)
        raise OutcomeUncertain("whatsapp_receipt_invalid") from exc
    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 200:
        _release_test_reply(db, organization_id, test_reply, uncertain=True)
        raise OutcomeUncertain("whatsapp_receipt_invalid")
    if test_reply:
        from app.domains.integrations.whatsapp_test import complete_test_send

        complete_test_send(db, organization_id, message_id)
    return message_id


def _provider_failure(response: httpx.Response) -> AppError:
    code = None
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and isinstance(error.get("code"), int):
        code = error["code"]
    if code == 131030:
        return AppError(
            502,
            "whatsapp_recipient_not_allowed",
            "Meta's test number can reply only to a phone number on its allowed recipient list.",
        )
    if code in {10, 190, 200}:
        return AppError(
            502,
            "whatsapp_send_forbidden",
            "The WhatsApp token cannot send this message.",
        )
    return AppError(502, "whatsapp_provider_error", "WhatsApp did not accept the message")


def _release_test_reply(
    db: Session, organization_id: uuid.UUID, test_reply: bool, *, uncertain: bool
) -> None:
    if not test_reply:
        return
    from app.domains.integrations.whatsapp_test import release_test_send

    release_test_send(db, organization_id, uncertain=uncertain)
