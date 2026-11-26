"""One restricted WhatsApp reply from Meta's test number.

Production messaging stays behind the live email mode and the WhatsApp live
flag. This path can send a single session message to a number that already
wrote to the workspace, and only while that live gate is closed. It never
sends a template, because template delivery can be billed.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.service import record_event
from app.domains.automation.signatures import open_integration_secret
from app.domains.inbox.models import InboxConversation, InboxMessage
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.schemas import WhatsAppTestStatus
from app.integrations.whatsapp import normalize_phone

RECIPIENT_KEY = "whatsapp_test_recipient"
REPLY_ID_KEY = "whatsapp_test_reply_message_id"
RESERVED_KEY = "whatsapp_test_reply_reserved"
CONFIRMED_KEY = "whatsapp_test_number_confirmed"
SERVER_KEYS = frozenset({RECIPIENT_KEY, REPLY_ID_KEY, RESERVED_KEY, CONFIRMED_KEY})
PUBLIC_CONFIG_KEYS = frozenset({"business_account_id", "phone_number_id"})
_DISABLED = (
    "WhatsApp replies are disabled for this environment. Incoming messages remain available."
)


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key in PUBLIC_CONFIG_KEYS}


def whatsapp_config_for_storage(
    current: dict[str, Any] | None, incoming: dict[str, Any]
) -> dict[str, Any]:
    stored = {
        "phone_number_id": incoming.get("phone_number_id"),
        "business_account_id": incoming.get("business_account_id"),
    }
    if isinstance(current, dict):
        for key in SERVER_KEYS:
            if key in current:
                stored[key] = current[key]
    return stored


def test_status(db: Session, organization_id: uuid.UUID) -> WhatsAppTestStatus:
    settings = get_settings()
    record = _row(db, organization_id)
    config = record.config if record is not None else {}
    recipient = _text(config, RECIPIENT_KEY)
    sent = bool(_text(config, REPLY_ID_KEY))
    return WhatsAppTestStatus(
        test_number_confirmed=config.get(CONFIRMED_KEY) is True,
        recipient_approved=bool(recipient),
        recipient_suffix=recipient[-4:] if recipient else None,
        test_reply_sent=sent,
        test_reply_pending=config.get(RESERVED_KEY) is True and not sent,
        production_messaging_enabled=(
            settings.email_mode == "live" and settings.whatsapp_live_enabled
        ),
    )


def approve_test_recipient(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    phone: str | None,
    *,
    expected_version: int,
) -> WhatsAppTestStatus:
    record = _configured_row(db, organization_id, lock=True)
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "WhatsApp settings changed. Reload before approving a recipient",
        )
    if _text(record.config, REPLY_ID_KEY) or record.config.get(RESERVED_KEY) is True:
        raise AppError(
            409,
            "whatsapp_test_reply_already_sent",
            "The restricted test reply was already used",
        )
    config = dict(record.config)
    if phone is None:
        config.pop(RECIPIENT_KEY, None)
        config.pop(CONFIRMED_KEY, None)
        record.config = config
        record_event(
            db,
            organization_id,
            "whatsapp_test_recipient_cleared",
            {},
            actor_id=actor_id,
        )
        db.commit()
        return test_status(db, organization_id)
    recipient = normalize_phone(phone)
    if not _sender_has_written(db, organization_id, recipient):
        raise AppError(
            422,
            "whatsapp_test_recipient_unknown",
            "Approve a number that has already sent a WhatsApp message to this workspace",
        )
    token, phone_id = _credentials(record)
    if not meta_test_number(_graph_phone(token, phone_id)):
        raise AppError(
            409,
            "whatsapp_test_number_required",
            "Restricted replies are available only from Meta's test number",
        )
    config[RECIPIENT_KEY] = recipient
    config[CONFIRMED_KEY] = True
    record.config = config
    record_event(
        db,
        organization_id,
        "whatsapp_test_recipient_approved",
        {"recipient_suffix": recipient[-4:]},
        actor_id=actor_id,
    )
    db.commit()
    return test_status(db, organization_id)


def whatsapp_reply_availability(
    db: Session, row: InboxConversation
) -> tuple[str | None, str | None]:
    if row.channel != "whatsapp":
        return None, None
    settings = get_settings()
    production = settings.email_mode == "live" and settings.whatsapp_live_enabled
    verified = _verified(db, row.organization_id)
    if production:
        if verified is None:
            return None, (
                "Workspace administrators must verify the WhatsApp connection "
                "before sending replies."
            )
        return "live", None
    if settings.whatsapp_live_enabled or verified is None:
        return None, _DISABLED
    record = _row(db, row.organization_id)
    config = record.config if record is not None else {}
    if _text(config, REPLY_ID_KEY):
        return None, (
            "The restricted test reply was already sent. Customer messaging stays disabled."
        )
    if config.get(RESERVED_KEY) is True:
        return None, "A restricted test reply is already in progress."
    recipient = _text(config, RECIPIENT_KEY)
    if config.get(CONFIRMED_KEY) is not True or not recipient:
        return None, _DISABLED
    if not _conversation_matches(db, row, recipient):
        return None, _DISABLED
    latest = _latest_inbound(db, row)
    if latest is None or datetime.now(UTC) - latest.created_at > timedelta(hours=24):
        return None, (
            "The customer-service window has closed. "
            "A restricted test reply cannot use a paid template."
        )
    return "test", None


def prepare_test_send(
    db: Session,
    organization_id: uuid.UUID,
    recipient: str,
    token: str,
    phone_id: str,
) -> None:
    record = _configured_row(db, organization_id, lock=True)
    approved = _text(record.config, RECIPIENT_KEY)
    if not approved or normalize_phone(approved) != normalize_phone(recipient):
        raise AppError(
            409,
            "whatsapp_test_recipient_required",
            "Restricted test replies can go only to the approved recipient",
        )
    if _text(record.config, REPLY_ID_KEY) or record.config.get(RESERVED_KEY) is True:
        raise AppError(
            409,
            "whatsapp_test_reply_already_sent",
            "The restricted test reply was already used",
        )
    if not _sender_has_written(db, organization_id, normalize_phone(recipient)):
        raise AppError(
            409,
            "whatsapp_test_recipient_required",
            "Restricted test replies can go only to the approved recipient",
        )
    if not meta_test_number(_graph_phone(token, phone_id)):
        raise AppError(
            409,
            "whatsapp_test_number_required",
            "Restricted replies are available only from Meta's test number",
        )
    config = dict(record.config)
    config[RESERVED_KEY] = True
    config[CONFIRMED_KEY] = True
    record.config = config
    db.commit()


def release_test_send(db: Session, organization_id: uuid.UUID, *, uncertain: bool) -> None:
    if uncertain:
        return
    record = _row(db, organization_id, lock=True)
    if record is None or _text(record.config, REPLY_ID_KEY):
        return
    config = dict(record.config)
    config.pop(RESERVED_KEY, None)
    record.config = config
    db.commit()


def complete_test_send(db: Session, organization_id: uuid.UUID, message_id: str) -> None:
    record = _configured_row(db, organization_id, lock=True)
    config = dict(record.config)
    config[REPLY_ID_KEY] = message_id
    config.pop(RESERVED_KEY, None)
    record.config = config
    record_event(
        db,
        organization_id,
        "whatsapp_test_reply_sent",
        {"message_id": message_id},
        actor_id=None,
    )
    db.commit()


def meta_test_number(payload: dict[str, Any]) -> bool:
    mode = payload.get("account_mode")
    name = payload.get("verified_name")
    if isinstance(mode, str) and mode.upper() == "SANDBOX":
        return True
    return isinstance(name, str) and name.strip().casefold() == "test number"


def _graph_phone(token: str, phone_id: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"https://graph.facebook.com/v21.0/{phone_id}",
            params={"fields": "id,verified_name,account_mode"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except httpx.TimeoutException as exc:
        raise AppError(
            504, "whatsapp_provider_timeout", "WhatsApp connection test timed out"
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(502, "whatsapp_unreachable", "WhatsApp could not be reached") from exc
    if response.status_code >= 400:
        raise AppError(502, "whatsapp_provider_error", "WhatsApp rejected the connection test")
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(
            502, "whatsapp_provider_error", "WhatsApp could not confirm this phone number"
        ) from exc
    if not isinstance(payload, dict) or payload.get("id") != phone_id:
        raise AppError(
            502, "whatsapp_provider_error", "WhatsApp could not confirm this phone number"
        )
    return payload


def _conversation_matches(db: Session, row: InboxConversation, recipient: str) -> bool:
    from app.domains.crm.models import Contact

    contact = (
        db.scalar(
            select(Contact).where(
                Contact.id == row.contact_id,
                Contact.organization_id == row.organization_id,
                Contact.archived_at.is_(None),
            )
        )
        if row.contact_id
        else None
    )
    if contact is None or not contact.phone:
        return False
    try:
        if normalize_phone(contact.phone) != recipient:
            return False
    except AppError:
        return False
    latest = _latest_inbound(db, row)
    if latest is None:
        return False
    try:
        return normalize_phone(latest.sender) == recipient
    except AppError:
        return False


def _latest_inbound(db: Session, row: InboxConversation) -> InboxMessage | None:
    return db.scalar(
        select(InboxMessage)
        .where(
            InboxMessage.organization_id == row.organization_id,
            InboxMessage.conversation_id == row.id,
            InboxMessage.channel == "whatsapp",
            InboxMessage.direction == "inbound",
        )
        .order_by(InboxMessage.created_at.desc(), InboxMessage.id)
        .limit(1)
    )


def _sender_has_written(db: Session, organization_id: uuid.UUID, recipient: str) -> bool:
    senders = db.scalars(
        select(InboxMessage.sender).where(
            InboxMessage.organization_id == organization_id,
            InboxMessage.channel == "whatsapp",
            InboxMessage.direction == "inbound",
        )
    ).all()
    for sender in senders:
        try:
            if normalize_phone(sender) == recipient:
                return True
        except AppError:
            continue
    return False


def _verified(db: Session, organization_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(IntegrationConfig.id).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
            IntegrationConfig.status == IntegrationStatus.configured,
            IntegrationConfig.verified_at.is_not(None),
        )
    )


def _row(
    db: Session,
    organization_id: uuid.UUID,
    *,
    lock: bool = False,
) -> IntegrationConfig | None:
    query = select(IntegrationConfig).where(
        IntegrationConfig.organization_id == organization_id,
        IntegrationConfig.integration_type == IntegrationType.whatsapp,
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def _configured_row(
    db: Session, organization_id: uuid.UUID, *, lock: bool = False
) -> IntegrationConfig:
    record = _row(db, organization_id, lock=lock)
    if (
        record is None
        or record.status != IntegrationStatus.configured
        or record.verified_at is None
    ):
        raise AppError(409, "whatsapp_unconfigured", "Verify the workspace WhatsApp connection")
    return record


def _credentials(record: IntegrationConfig) -> tuple[str, str]:
    if not record.encrypted_credentials:
        raise AppError(503, "whatsapp_unconfigured", "Verify the workspace WhatsApp connection")
    try:
        credentials = json.loads(open_integration_secret(record.encrypted_credentials))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            503, "whatsapp_credentials_invalid", "WhatsApp credentials are invalid"
        ) from exc
    token = credentials.get("access_token") if isinstance(credentials, dict) else None
    phone_id = record.config.get("phone_number_id")
    if not isinstance(token, str) or not token.strip() or not isinstance(phone_id, str):
        raise AppError(
            503, "whatsapp_configuration_incomplete", "WhatsApp configuration is incomplete"
        )
    return token, phone_id


def _text(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    return value.strip() if isinstance(value, str) else ""
