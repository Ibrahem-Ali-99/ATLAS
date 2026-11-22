import hashlib
import hmac


def sign_webhook(secret: str, timestamp: str, idempotency_key: str, body: bytes) -> str:
    message = timestamp.encode() + b"." + idempotency_key.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signatures_match(expected: str, presented: str) -> bool:
    if len(expected) != len(presented):
        return False
    return hmac.compare_digest(expected, presented)
