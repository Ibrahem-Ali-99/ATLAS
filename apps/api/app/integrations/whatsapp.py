"""Official Meta WhatsApp Cloud API adapter.

The adapter is only invoked by the approved execution path. It never accepts
credentials from callers and refuses to send while ATLAS is in sandbox mode.
"""
# ruff: noqa: E501

import json
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.automation.signatures import open_integration_secret
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType


def parse_cloud_webhook(payload: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
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
                    messages.append({"id": str(item["id"]), "sender": sender, "body": text, "phone_number_id": phone_id})
            for item in value.get("statuses", []):
                if item.get("id") and item.get("status"):
                    statuses.append({"id": str(item["id"]), "status": str(item["status"]), "phone_number_id": phone_id})
    return messages, statuses


def send_whatsapp_text(
    db: Session,
    organization_id: uuid.UUID,
    recipient: str,
    body: str,
    *,
    template_name: str | None = None,
    template_language: str = "en_US",
) -> str:
    if get_settings().email_mode != "live":
        raise AppError(
            409, "sandbox_delivery_only", "WhatsApp delivery is disabled in sandbox mode"
        )
    record = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
            IntegrationConfig.status == IntegrationStatus.configured,
        )
    )
    if record is None or not record.encrypted_credentials:
        raise AppError(503, "whatsapp_unconfigured", "WhatsApp is not configured")
    try:
        credentials = json.loads(open_integration_secret(record.encrypted_credentials))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            503, "whatsapp_credentials_invalid", "WhatsApp credentials are invalid"
        ) from exc
    token = credentials.get("access_token") if isinstance(credentials, dict) else None
    phone_id = record.config.get("phone_number_id")
    if not isinstance(token, str) or not isinstance(phone_id, str):
        raise AppError(
            503, "whatsapp_configuration_incomplete", "WhatsApp configuration is incomplete"
        )
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
    except httpx.TimeoutException as exc:
        raise AppError(
            504, "whatsapp_provider_timeout", "WhatsApp delivery outcome is unknown"
        ) from exc
    if response.status_code >= 400:
        raise AppError(502, "whatsapp_provider_error", "WhatsApp did not accept the message")
    try:
        message_id = response.json()["messages"][0]["id"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AppError(
            409, "whatsapp_provider_uncertain", "WhatsApp returned an ambiguous delivery result"
        ) from exc
    return str(message_id)
