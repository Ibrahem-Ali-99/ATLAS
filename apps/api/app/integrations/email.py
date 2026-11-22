import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.outcomes import DeliveryFailed, OutcomeUncertain

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "mailpit", "::1"})


@dataclass(frozen=True)
class OutboundEmail:
    recipient: str
    subject: str
    body: str
    idempotency_key: str


@dataclass(frozen=True)
class DeliveryReceipt:
    message_id: str
    mode: str


def send_email(message: OutboundEmail) -> DeliveryReceipt:
    """Deliver through the configured SMTP transport.

    Sandbox mode refuses any host that is not local. Live mode refuses to run
    unless it was explicitly enabled. A timeout is uncertain: the server may
    already have accepted the message.
    """

    settings = get_settings()
    if settings.email_mode == "live" and not settings.email_live_enabled:
        raise AppError(503, "email_unconfigured", "Live email is not enabled")
    if settings.email_mode == "sandbox" and settings.smtp_host.lower() not in _LOCAL_HOSTS:
        raise AppError(
            503, "email_unconfigured", "Sandbox email only delivers to a local SMTP host"
        )
    recipient = message.recipient.strip()
    if "@" not in recipient:
        raise AppError(422, "invalid_recipient", "The approved action has no recipient")
    token = message.idempotency_key[:24]
    message_id = f"<{token}@atlas.local>"
    payload = EmailMessage()
    payload["From"] = settings.smtp_from
    payload["To"] = recipient
    payload["Subject"] = message.subject[:200]
    payload["Message-ID"] = message_id
    payload.set_content(message.body)
    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as client:
            client.send_message(payload)
    except TimeoutError as exc:
        raise OutcomeUncertain("smtp_timeout") from exc
    except (smtplib.SMTPException, OSError) as exc:
        if "timed out" in str(exc).lower():
            raise OutcomeUncertain("smtp_timeout") from exc
        raise DeliveryFailed("smtp_failed") from exc
    return DeliveryReceipt(message_id=message_id, mode=settings.email_mode)
