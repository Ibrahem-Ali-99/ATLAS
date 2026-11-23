import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError

_SEAL_PREFIX = "enc:v1:"


def seal_webhook_secret(secret: str) -> str:
    return seal_integration_secret(secret)


def open_webhook_secret(stored: str) -> str:
    return open_integration_secret(
        stored, failure_code="webhook_unauthorized", failure_message="Webhook authentication failed"
    )


def seal_integration_secret(secret: str) -> str:
    token = _fernet().encrypt(secret.encode()).decode()
    return _SEAL_PREFIX + token


def open_integration_secret(
    stored: str,
    *,
    failure_code: str = "integration_secret_invalid",
    failure_message: str = "Stored integration secret is invalid",
) -> str:
    if not stored.startswith(_SEAL_PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored.removeprefix(_SEAL_PREFIX).encode()).decode()
    except InvalidToken as exc:
        raise AppError(500, failure_code, failure_message) from exc


def _fernet() -> Fernet:
    material = hashlib.sha256(b"atlas-webhook-v1:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def sign_webhook(secret: str, timestamp: str, idempotency_key: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + idempotency_key.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signatures_match(expected: str, presented: str) -> bool:
    if len(expected) != len(presented):
        return False
    return hmac.compare_digest(expected, presented)
