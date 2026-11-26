import uuid

from itsdangerous import BadSignature, URLSafeTimedSerializer
from pwdlib import PasswordHash
from starlette.responses import Response

from app.core.config import Settings

password_hasher = PasswordHash.recommended()

SESSION_SALT = "atlas-session-v1"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bool(password_hasher.verify(password, password_hash))
    except (ValueError, TypeError):
        return False


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt=SESSION_SALT)


def sign_session_id(session_id: uuid.UUID, secret_key: str) -> str:
    return _serializer(secret_key).dumps(str(session_id))


def read_session_id(token: str, secret_key: str, max_age_seconds: int) -> uuid.UUID | None:
    try:
        raw = _serializer(secret_key).loads(token, max_age=max_age_seconds)
    except BadSignature:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def attach_session_cookie(
    response: Response,
    settings: Settings,
    session_id: uuid.UUID,
    *,
    max_age: int | None = None,
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sign_session_id(session_id, settings.secret_key),
        max_age=settings.session_max_age_seconds if max_age is None else max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
