"""Failed-login counters kept in this process.

Another API process does not see these counters. The client key is the direct
connection peer. A forwarded address is not trusted, because the caller can set it.
"""

from __future__ import annotations

import time

from app.core.config import get_settings

_failures: dict[str, list[float]] = {}


def clear_login_attempts() -> None:
    _failures.clear()


def login_is_limited(client_key: str, email: str) -> bool:
    settings = get_settings()
    window = float(settings.login_window_seconds)
    return _over(f"client:{client_key}", settings.login_client_limit, window) or _over(
        f"email:{email}", settings.login_email_limit, window
    )


def note_login_failure(client_key: str, email: str) -> None:
    now = time.monotonic()
    window = float(get_settings().login_window_seconds)
    for key in (f"client:{client_key}", f"email:{email}"):
        _trim(key, window)
        _failures.setdefault(key, []).append(now)


def note_login_success(email: str) -> None:
    _failures.pop(f"email:{email}", None)


def _over(key: str, limit: int, window: float) -> bool:
    _trim(key, window)
    return len(_failures.get(key, [])) >= limit


def _trim(key: str, window: float) -> None:
    now = time.monotonic()
    kept = [stamp for stamp in _failures.get(key, []) if now - stamp < window]
    if kept:
        _failures[key] = kept
    else:
        _failures.pop(key, None)
