import json
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.service import open_credentials, read_metadata
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "mailpit", "::1"})
logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class OutboundEmail:
    recipient: str
    subject: str
    body: str
    idempotency_key: str
    unsubscribe_url: str | None = None


@dataclass(frozen=True)
class DeliveryReceipt:
    message_id: str
    mode: str


def normalize_recipient(value: str) -> str:
    """Return a single normalized address, rejecting display-name ambiguity."""
    _, address = parseaddr(value.strip())
    if not address or address.count("@") != 1:
        raise AppError(422, "invalid_recipient", "The approved action has no valid recipient")
    local, domain = address.rsplit("@", 1)
    if (
        not local
        or not domain
        or ("." not in domain and domain.casefold() != "localhost")
        or any(char.isspace() for char in address)
    ):
        raise AppError(422, "invalid_recipient", "The approved action has no valid recipient")
    return address.casefold()


def _sandbox_settings(db: Session | None, organization_id: uuid.UUID | None) -> Settings:
    settings = get_settings()
    if db is not None and organization_id is not None:
        override = read_metadata(db, organization_id, IntegrationType.email)
        if override is not None and override.status != IntegrationStatus.configured:
            raise AppError(
                503, "email_integration_disabled", "Organization email delivery is disabled"
            )
        if override is not None and (
            override.provider != "smtp"
            or not isinstance(override.config.get("host"), str)
            or not isinstance(override.config.get("port"), int)
        ):
            raise AppError(503, "email_unconfigured", "Organization email configuration is invalid")
    if settings.email_mode == "live" and not settings.email_live_enabled:
        raise AppError(503, "email_unconfigured", "Live email is not enabled")
    if settings.email_mode == "sandbox" and settings.smtp_host.lower() not in _LOCAL_HOSTS:
        raise AppError(
            503,
            "email_unconfigured",
            "Sandbox email only delivers to a local SMTP host",
        )
    return settings


def _workspace_smtp(
    db: Session, organization_id: uuid.UUID, settings: Settings
) -> tuple[str, int, str, bool, str, str]:
    record = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == IntegrationType.email,
            IntegrationConfig.status == IntegrationStatus.configured,
            IntegrationConfig.verified_at.is_not(None),
        )
    )
    if record is None or record.provider != "smtp":
        raise AppError(503, "smtp_not_verified", "Verify the workspace SMTP connection")
    config = record.config
    host, port, sender = config.get("host"), config.get("port"), config.get("from_address")
    hosts = {
        part.strip().casefold() for part in settings.smtp_live_hosts.split(",") if part.strip()
    }
    if (
        config.get("live_delivery_enabled") is not True
        or not isinstance(host, str)
        or host.casefold() not in hosts
        or type(port) is not int
        or not 1 <= port <= 65535
        or not isinstance(sender, str)
        or ((config.get("use_tls") is True) == (config.get("starttls") is True))
    ):
        raise AppError(
            503, "smtp_delivery_unconfigured", "Configure an approved SMTP relay with TLS"
        )
    try:
        credentials = json.loads(open_credentials(record) or "{}")
    except (ValueError, TypeError):
        credentials = {}
    username = credentials.get("username") if isinstance(credentials, dict) else None
    password = credentials.get("password") if isinstance(credentials, dict) else None
    if (
        not isinstance(username, str)
        or not username
        or not isinstance(password, str)
        or not password
    ):
        raise AppError(503, "smtp_auth_unconfigured", "Configure SMTP relay authentication")
    return (
        host,
        port,
        normalize_recipient(sender),
        config.get("use_tls") is True,
        username,
        password,
    )


def send_email(
    message: OutboundEmail,
    *,
    db: Session | None = None,
    organization_id: uuid.UUID | None = None,
    sandbox_only: bool = False,
) -> DeliveryReceipt:
    """Deliver through the configured SMTP transport.

    Sandbox mode refuses any host that is not local. Live mode refuses to run
    unless it was explicitly enabled. A timeout is uncertain: the server may
    already have accepted the message.
    """

    settings = _sandbox_settings(db, organization_id)
    if sandbox_only and settings.email_mode != "sandbox":
        raise AppError(503, "sandbox_email_required", "Campaign delivery requires sandbox email")
    host, port, sender = settings.smtp_host, settings.smtp_port, settings.smtp_from
    use_tls = False
    username = password = None
    if settings.email_mode == "live" and organization_id is not None:
        if db is None:
            raise AppError(503, "email_unconfigured", "Workspace SMTP configuration is unavailable")
        host, port, sender, use_tls, username, password = _workspace_smtp(
            db, organization_id, settings
        )
    recipient = normalize_recipient(message.recipient)
    token = message.idempotency_key[:24]
    message_id = f"<{token}@atlas.local>"
    payload = EmailMessage()
    payload["From"] = sender
    payload["To"] = recipient
    payload["Subject"] = message.subject[:200]
    payload["Message-ID"] = message_id
    if message.unsubscribe_url:
        payload["List-Unsubscribe"] = f"<{message.unsubscribe_url}>"
    payload.set_content(message.body)
    try:
        logger.info("email_smtp_dispatch_started", host=host, port=port)
        context = ssl.create_default_context() if username else None
        connection: smtplib.SMTP
        if use_tls:
            connection = smtplib.SMTP_SSL(
                host, port, timeout=settings.smtp_timeout_seconds, context=context
            )
        else:
            connection = smtplib.SMTP(host, port, timeout=settings.smtp_timeout_seconds)
        with connection as client:
            if username and password:
                if not use_tls:
                    client.starttls(context=context)
                client.login(username, password)
            client.send_message(payload)
        logger.info("email_smtp_accepted", host=host, port=port)
    except TimeoutError as exc:
        raise OutcomeUncertain("smtp_timeout") from exc
    except (smtplib.SMTPServerDisconnected, ConnectionResetError) as exc:
        raise OutcomeUncertain("smtp_disconnected") from exc
    except (smtplib.SMTPException, OSError) as exc:
        if "timed out" in str(exc).lower():
            raise OutcomeUncertain("smtp_timeout") from exc
        raise DeliveryFailed("smtp_failed") from exc
    return DeliveryReceipt(message_id=message_id, mode=settings.email_mode)
