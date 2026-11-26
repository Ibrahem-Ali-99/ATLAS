"""Administrator-only Resend test delivery.

This path sends from Resend's shared test sender and never starts a campaign,
opens customer SMTP, or changes the workspace sender.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr

import httpx
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.audit.models import AuditEvent
from app.domains.audit.service import record_event
from app.domains.automation.signatures import seal_integration_secret
from app.domains.integrations.domain_models import DomainVerificationStatus, EmailDomainVerification
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.resend_credentials import TEST_RECIPIENT_KEY
from app.domains.integrations.schemas import ResendTestReceipt, ResendTestStatus
from app.domains.integrations.service import open_credentials

TEST_SENDER = "onboarding@resend.dev"
OFFICIAL_TEST_RECIPIENTS = (
    "delivered@resend.dev",
    "bounced@resend.dev",
    "complained@resend.dev",
)
ATTEMPT_LIMIT = 5
ATTEMPT_WINDOW = timedelta(hours=1)
ATTEMPT_GAP = timedelta(seconds=30)
_ADDRESS = TypeAdapter(EmailStr)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SUBJECT = "ATLAS administrator test"
_BODY = (
    "This message confirms the ATLAS Resend sending key. It is not a customer email or a campaign."
)


def test_status(db: Session, organization_id: uuid.UUID) -> ResendTestStatus:
    record = _email_row(db, organization_id, lock=False)
    credentials = _credentials(record)
    key_present = _key(credentials) is not None
    evidence = _evidence(credentials) if key_present else None
    approved = _approved_recipient(record)
    return ResendTestStatus(
        credential_configured=key_present,
        test_delivery_verified=evidence is not None,
        sending_domain_verified=_domain_verified(db, organization_id, record),
        production_delivery_enabled=_production_enabled(db, organization_id, record, key_present),
        test_sender=TEST_SENDER,
        approved_recipient=approved,
        official_recipients=list(OFFICIAL_TEST_RECIPIENTS),
        last_test_recipient=None if evidence is None else evidence[1],
        last_test_message_id=None if evidence is None else evidence[0],
        last_test_at=None if evidence is None else evidence[2],
        provider_confirmation=None if evidence is None else evidence[3],
        provider_last_event=_stored_last_event(credentials),
    )


def approve_test_recipient(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    address: str | None,
    *,
    expected_version: int,
) -> ResendTestStatus:
    record = _email_row(db, organization_id, lock=True)
    if record is None:
        raise AppError(
            404,
            "integration_not_found",
            "Save the email integration before approving a test recipient",
        )
    if record.credential_version != expected_version:
        raise AppError(
            409,
            "integration_version_conflict",
            "Email settings changed. Reload before approving a recipient",
        )
    normalized = None if address is None else _validated_address(address)
    config = dict(record.config)
    if normalized is None:
        config.pop(TEST_RECIPIENT_KEY, None)
    else:
        config[TEST_RECIPIENT_KEY] = normalized
    record.config = config
    record_event(
        db,
        organization_id,
        "resend_test_recipient_approved" if normalized else "resend_test_recipient_cleared",
        {"recipient": normalized},
        actor_id=actor_id,
    )
    db.commit()
    return test_status(db, organization_id)


def deliver_test(
    db: Session,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    recipient: str,
) -> ResendTestReceipt:
    record = _email_row(db, organization_id, lock=True)
    if record is None or record.status == IntegrationStatus.disabled:
        raise AppError(
            409, "resend_test_unavailable", "Enable the email integration before sending a test"
        )
    credentials = _credentials(record)
    key = _key(credentials)
    if key is None:
        raise AppError(
            409, "resend_test_unconfigured", "Save a Resend sending key before sending a test"
        )
    destination = _allowed_recipient(recipient, _approved_recipient(record))
    _require_rate_limit(db, organization_id)
    record_event(
        db,
        organization_id,
        "resend_test_email_attempted",
        {"recipient": destination, "sender": TEST_SENDER},
        actor_id=actor_id,
    )
    db.commit()
    try:
        message_id, confirmation, last_event = _send(key, destination)
    except AppError as exc:
        record_event(
            db,
            organization_id,
            "resend_test_email_failed",
            {"recipient": destination, "sender": TEST_SENDER, "code": exc.code},
            actor_id=actor_id,
        )
        db.commit()
        raise
    verified_at = datetime.now(UTC)
    current = _email_row(db, organization_id, lock=True)
    saved = current is not None and _write_evidence(
        current,
        message_id=message_id,
        recipient=destination,
        confirmation=confirmation,
        verified_at=verified_at,
        key_used=key,
        last_event=last_event,
    )
    record_event(
        db,
        organization_id,
        "resend_test_email_verified" if saved else "resend_test_email_superseded",
        {
            "recipient": destination,
            "sender": TEST_SENDER,
            "message_id": message_id,
            "provider_confirmation": confirmation,
        },
        actor_id=actor_id,
    )
    db.commit()
    if not saved:
        raise AppError(
            409,
            "resend_test_key_changed",
            "Resend accepted the test, but the sending key changed before the result was saved.",
        )
    status = test_status(db, organization_id)
    return ResendTestReceipt(
        message_id=message_id,
        recipient=destination,
        sender=TEST_SENDER,
        provider_confirmation=confirmation,
        status=status,
    )


def refresh_delivery(db: Session, organization_id: uuid.UUID, *, attempts: int = 4) -> str:
    """Read Resend's latest event for the stored test. Does not send another message."""

    record = _email_row(db, organization_id, lock=True)
    credentials = _credentials(record)
    evidence = _evidence(credentials)
    key = _key(credentials)
    if record is None or evidence is None or key is None:
        raise AppError(
            409,
            "resend_test_unconfirmed",
            "Resend has not accepted an administrator test for this key",
        )
    message_id, recipient = evidence[0], evidence[1]
    observed = "not_reported"
    for attempt in range(max(1, attempts)):
        retrieved = _request(
            "GET",
            f"https://api.resend.com/emails/{message_id}",
            api_key=key,
            body=None,
            idempotency_key=None,
        )
        if retrieved.status_code in {401, 403} and _error_name(retrieved) == "restricted_api_key":
            observed = "unavailable"
            break
        _raise_for_provider(retrieved, sending=False)
        if not _retrieved_matches(retrieved, message_id, recipient):
            raise AppError(
                502, "resend_receipt_mismatch", "Resend confirmed a different sender or recipient"
            )
        payload = _payload(retrieved) or {}
        observed = _event_name(payload.get("last_event")) or "not_reported"
        pending = observed in {"sent", "delivery_delayed", "not_reported"}
        if not pending or attempt + 1 == max(1, attempts):
            break
        time.sleep(3)
    if not _store_last_event(record, observed, key):
        raise AppError(
            409,
            "resend_test_key_changed",
            "Resend returned a delivery event, but the sending key changed before it was saved.",
        )
    db.commit()
    return observed


def _send(api_key: str, recipient: str) -> tuple[str, str, str | None]:
    created = _request(
        "POST",
        "https://api.resend.com/emails",
        api_key=api_key,
        body={
            "from": TEST_SENDER,
            "to": [recipient],
            "subject": _SUBJECT,
            "text": _BODY,
        },
        idempotency_key=str(uuid.uuid4()),
    )
    _raise_for_provider(created, sending=True)
    message_id = _message_id(created)
    retrieved = _request(
        "GET",
        f"https://api.resend.com/emails/{message_id}",
        api_key=api_key,
        body=None,
        idempotency_key=None,
    )
    if retrieved.status_code in {401, 403} and _error_name(retrieved) == "restricted_api_key":
        return message_id, "accepted", None
    _raise_for_provider(retrieved, sending=False)
    if not _retrieved_matches(retrieved, message_id, recipient):
        raise AppError(
            502, "resend_receipt_mismatch", "Resend confirmed a different sender or recipient"
        )
    payload = _payload(retrieved) or {}
    return message_id, "retrieved", _event_name(payload.get("last_event"))


def _request(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict[str, object] | None,
    idempotency_key: str | None,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    try:
        return httpx.request(method, url, headers=headers, json=body, timeout=10)
    except httpx.RequestError as exc:
        raise AppError(502, "resend_unavailable", "Resend could not be reached") from exc


def _raise_for_provider(response: httpx.Response, *, sending: bool) -> None:
    if response.is_success:
        return
    name = _error_name(response)
    message = _safe_message(response)
    if response.status_code == 429:
        raise AppError(
            429,
            "resend_provider_rate_limited",
            "Resend is limiting test delivery. Wait and try again.",
        )
    if response.status_code in {401, 403}:
        if name == "restricted_api_key" and sending:
            raise AppError(
                403, "resend_send_forbidden", "This Resend key is not allowed to send email."
            )
        raise AppError(422, "resend_credentials_rejected", "Resend rejected the sending key.")
    if response.status_code == 422 and _owner_only(name, message):
        named = _single_address(message)
        suffix = f" Resend named {named}." if named else ""
        raise AppError(
            422,
            "resend_test_owner_mismatch",
            "Resend only accepts the account owner for this test sender."
            f"{suffix} Approve that address and send again.",
        )
    if response.status_code == 422:
        detail = message or "Resend rejected the test message."
        raise AppError(422, "resend_test_rejected", detail)
    if response.status_code >= 500 or response.status_code == 408:
        raise AppError(502, "resend_unavailable", "Resend could not accept the test message")
    raise AppError(502, "resend_test_rejected", "Resend rejected the test message.")


def _message_id(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str(uuid.UUID(str(payload.get("id"))))
    except (TypeError, ValueError):
        pass
    raise AppError(502, "resend_receipt_invalid", "Resend did not return a message id")


def _retrieved_matches(response: httpx.Response, message_id: str, recipient: str) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict) or str(payload.get("id", "")) != message_id:
        return False
    return _address(payload.get("from")) == TEST_SENDER and _address(payload.get("to")) == recipient


def _address(value: object) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if not isinstance(value, str):
        return ""
    _, parsed = parseaddr(value)
    return (parsed or value).strip().casefold()


def _error_name(response: httpx.Response) -> str:
    payload = _payload(response)
    name = payload.get("name") if isinstance(payload, dict) else None
    return name if isinstance(name, str) else ""


def _safe_message(response: httpx.Response) -> str:
    payload = _payload(response)
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str) or "re_" in message or "bearer " in message.lower():
        return ""
    return " ".join(message.split())[:180]


def _payload(response: httpx.Response) -> dict[str, object] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _owner_only(name: str, message: str) -> bool:
    text = message.casefold()
    return name == "validation_error" and ("own email" in text or "testing emails" in text)


def _single_address(message: str) -> str | None:
    found = {item.casefold() for item in _EMAIL.findall(message)}
    found.discard(TEST_SENDER)
    if len(found) != 1:
        return None
    return found.pop()


def _allowed_recipient(recipient: str, approved: str | None) -> str:
    normalized = _validated_address(recipient)
    if normalized.casefold() in OFFICIAL_TEST_RECIPIENTS:
        return normalized.casefold()
    if approved is not None and normalized.casefold() == approved.casefold():
        return approved
    raise AppError(
        422,
        "resend_test_recipient_unapproved",
        "Choose the approved account-owner address or an official Resend test recipient.",
    )


def _validated_address(value: str) -> str:
    try:
        return str(_ADDRESS.validate_python(value.strip()))
    except ValidationError:
        raise AppError(
            422, "resend_test_recipient_invalid", "Enter a valid email address"
        ) from None


def _require_rate_limit(db: Session, organization_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    latest = db.scalar(
        select(func.max(AuditEvent.created_at)).where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.action == "resend_test_email_attempted",
        )
    )
    if latest is not None and now - _aware(latest) < ATTEMPT_GAP:
        raise AppError(429, "resend_test_rate_limited", "Wait before sending another test message.")
    count = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.action == "resend_test_email_attempted",
            AuditEvent.created_at >= now - ATTEMPT_WINDOW,
        )
    )
    if count is not None and int(count) >= ATTEMPT_LIMIT:
        raise AppError(
            429,
            "resend_test_rate_limited",
            "The administrator test limit was reached. Wait and try again.",
        )


def _write_evidence(
    record: IntegrationConfig,
    *,
    message_id: str,
    recipient: str,
    confirmation: str,
    verified_at: datetime,
    key_used: str,
    last_event: str | None = None,
) -> bool:
    credentials = _credentials(record)
    if _key(credentials) != key_used:
        return False
    credentials.update(
        {
            "resend_test_message_id": message_id,
            "resend_test_verified_at": verified_at.isoformat(),
            "resend_test_recipient": recipient,
            "resend_test_confirmation": confirmation,
        }
    )
    if last_event is not None:
        credentials["resend_test_last_event"] = last_event
    record.encrypted_credentials = seal_integration_secret(json.dumps(credentials))
    return True


def _stored_last_event(credentials: dict[str, object]) -> str | None:
    return _event_name(credentials.get("resend_test_last_event"))


def _event_name(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[a-z0-9._-]{1,40}", value):
        return value
    return None


def _store_last_event(record: IntegrationConfig, event: str, key_used: str) -> bool:
    credentials = _credentials(record)
    if _key(credentials) != key_used:
        return False
    credentials["resend_test_last_event"] = event
    record.encrypted_credentials = seal_integration_secret(json.dumps(credentials))
    return True


def _evidence(credentials: dict[str, object]) -> tuple[str, str, datetime, str] | None:
    message_id = credentials.get("resend_test_message_id")
    recipient = credentials.get("resend_test_recipient")
    verified_at = credentials.get("resend_test_verified_at")
    confirmation = credentials.get("resend_test_confirmation")
    if (
        not isinstance(message_id, str)
        or not isinstance(recipient, str)
        or not isinstance(verified_at, str)
        or confirmation not in {"accepted", "retrieved"}
    ):
        return None
    try:
        parsed_id = str(uuid.UUID(message_id))
        parsed_at = datetime.fromisoformat(verified_at)
    except ValueError:
        return None
    if parsed_at.tzinfo is None:
        return None
    return parsed_id, recipient, parsed_at, confirmation


def _approved_recipient(record: IntegrationConfig | None) -> str | None:
    if record is None or not isinstance(record.config, dict):
        return None
    approved = record.config.get(TEST_RECIPIENT_KEY)
    if not isinstance(approved, str):
        return None
    try:
        return str(_ADDRESS.validate_python(approved))
    except ValidationError:
        return None


def _domain_verified(
    db: Session, organization_id: uuid.UUID, record: IntegrationConfig | None
) -> bool:
    if record is None:
        return False
    domain_id = db.scalar(
        select(EmailDomainVerification.id).where(
            EmailDomainVerification.organization_id == organization_id,
            EmailDomainVerification.provider == "resend",
            EmailDomainVerification.status == DomainVerificationStatus.verified,
            EmailDomainVerification.credential_version == record.credential_version,
            EmailDomainVerification.verified_at.is_not(None),
        )
    )
    return domain_id is not None


def _production_enabled(
    db: Session,
    organization_id: uuid.UUID,
    record: IntegrationConfig | None,
    key_present: bool,
) -> bool:
    """Mirror the campaign sender gate. A verified test does not satisfy it."""
    settings = get_settings()
    if not (
        settings.email_mode == "live"
        and settings.email_live_enabled
        and settings.campaign_live_enabled
    ):
        return False
    if (
        len(settings.campaign_link_secret) < 32
        or not _webhook_configured()
        or not _campaign_origin_ready()
    ):
        return False
    if (
        record is None
        or record.provider != "smtp"
        or record.status != IntegrationStatus.configured
        or not key_present
    ):
        return False
    try:
        address = str(_ADDRESS.validate_python(record.config.get("from_address")))
    except ValidationError:
        return False
    domain = address.rsplit("@", 1)[1].lower()
    verified = db.scalar(
        select(EmailDomainVerification.id).where(
            EmailDomainVerification.organization_id == organization_id,
            EmailDomainVerification.domain == domain,
            EmailDomainVerification.provider == "resend",
            EmailDomainVerification.status == DomainVerificationStatus.verified,
            EmailDomainVerification.credential_version == record.credential_version,
        )
    )
    return verified is not None


def _webhook_configured() -> bool:
    import base64
    import binascii

    value = get_settings().resend_campaign_webhook_secret
    try:
        if value.startswith("whsec_"):
            return len(base64.b64decode(value[6:], validate=True)) >= 16
    except (ValueError, binascii.Error):
        return False
    return False


def _campaign_origin_ready() -> bool:
    from urllib.parse import urlsplit

    settings = get_settings()
    value = settings.campaign_public_url or (
        "http://127.0.0.1:8000" if settings.email_mode == "sandbox" else ""
    )
    try:
        parsed = urlsplit(value.rstrip("/"))
    except ValueError:
        return False
    return bool(
        parsed.hostname
        and not parsed.username
        and not parsed.password
        and not (parsed.path or parsed.query or parsed.fragment)
        and (
            parsed.scheme == "https"
            or (
                settings.email_mode == "sandbox"
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
    )


def _credentials(record: IntegrationConfig | None) -> dict[str, object]:
    if record is None:
        return {}
    try:
        loaded = json.loads(open_credentials(record) or "{}")
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _key(credentials: dict[str, object]) -> str | None:
    value = credentials.get("resend_api_key")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _email_row(db: Session, organization_id: uuid.UUID, *, lock: bool) -> IntegrationConfig | None:
    query = select(IntegrationConfig).where(
        IntegrationConfig.organization_id == organization_id,
        IntegrationConfig.integration_type == IntegrationType.email,
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
