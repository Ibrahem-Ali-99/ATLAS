import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.core.errors import AppError

_SEAL_PREFIX = "enc:v1:"
_CREDENTIAL_PREFIX = "enc:v2:"


def seal_webhook_secret(secret: str) -> str:
    return seal_integration_secret(secret)


def open_webhook_secret(stored: str) -> str:
    return open_integration_secret(
        stored, failure_code="webhook_unauthorized", failure_message="Webhook authentication failed"
    )


def seal_integration_secret(secret: str) -> str:
    key_id, key = _credential_keyring()[0]
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, secret.encode(), key_id.encode())
    return f"{_CREDENTIAL_PREFIX}{key_id}:{_b64(nonce)}:{_b64(ciphertext)}"


def open_integration_secret(
    stored: str,
    *,
    failure_code: str = "integration_secret_invalid",
    failure_message: str = "Stored integration secret is invalid",
) -> str:
    if stored.startswith(_SEAL_PREFIX):
        return _open_legacy(stored, failure_code, failure_message)
    if not stored.startswith(_CREDENTIAL_PREFIX):
        return stored
    try:
        key_id, nonce, ciphertext = stored.removeprefix(_CREDENTIAL_PREFIX).split(":", 2)
        key = dict(_credential_keyring()).get(key_id)
        if key is None:
            raise ValueError("unknown credential key")
        return AESGCM(key).decrypt(_unb64(nonce), _unb64(ciphertext), key_id.encode()).decode()
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(500, failure_code, failure_message) from exc
    except Exception as exc:
        raise AppError(500, failure_code, failure_message) from exc


def _open_legacy(stored: str, failure_code: str, failure_message: str) -> str:
    try:
        return _fernet().decrypt(stored.removeprefix(_SEAL_PREFIX).encode()).decode()
    except InvalidToken as exc:
        raise AppError(500, failure_code, failure_message) from exc


def _credential_keyring() -> list[tuple[str, bytes]]:
    configured = get_settings().credential_encryption_keys.strip()
    if not configured:
        # Backward-compatible development/test fallback. Production requires
        # an explicit independent keyring via configuration validation.
        configured = f"legacy-secret-key={get_settings().secret_key}"
    entries: list[tuple[str, bytes]] = []
    for item in configured.split(","):
        key_id, separator, value = item.partition("=")
        if not separator or not key_id.strip() or not value:
            continue
        entries.append((key_id.strip(), hashlib.sha256(value.encode()).digest()))
    if not entries:
        raise AppError(500, "integration_secret_invalid", "Credential encryption is unavailable")
    return entries


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


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
