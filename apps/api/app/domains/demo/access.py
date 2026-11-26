"""Visitor-session predicates and in-process limits.

Launch counts use the direct connection peer, the same rule as login.
A forwarded address is not trusted, because the caller can set it.
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.domains.identity.models import Organization

VISITOR_PREFIX = "harbor-visitor-"
VISITOR_EMAIL_DOMAIN = "@visitors.example"
SESSION_MINUTES = 45
MAX_ACTIVE_VISITORS = 40
MAX_REQUESTS = 400
MAX_ASSISTANT_REPLIES = 12
MAX_DOCUMENTS = 3
MAX_UPLOAD_BYTES = 200_000
MAX_KNOWLEDGE_BYTES = 500_000
LAUNCH_LIMIT = 8
LAUNCH_WINDOW_SECONDS = 900

_launches: dict[str, list[float]] = {}
_requests: dict[str, int] = {}


def is_visitor_slug(slug: str) -> bool:
    return slug.startswith(VISITOR_PREFIX)


def is_visitor_email(email: str) -> bool:
    return email.endswith(VISITOR_EMAIL_DOMAIN)


def organization_is_visitor(db: Session, organization_id: uuid.UUID) -> bool:
    organization = db.get(Organization, organization_id)
    return organization is not None and is_visitor_slug(organization.slug)


def clear_demo_counters() -> None:
    _launches.clear()
    _requests.clear()


def launch_is_limited(client_key: str) -> bool:
    _trim(client_key)
    return len(_launches.get(client_key, [])) >= LAUNCH_LIMIT


def note_launch(client_key: str) -> None:
    _trim(client_key)
    _launches.setdefault(client_key, []).append(time.monotonic())


def note_demo_request(session_id: str) -> None:
    if len(_requests) > 5000:
        _requests.clear()
    count = _requests.get(session_id, 0) + 1
    _requests[session_id] = count
    if count > MAX_REQUESTS:
        raise AppError(
            429,
            "demo_limited",
            "This demo session reached its request limit. Restart the demonstration.",
        )


def forget_demo_request(session_id: str) -> None:
    _requests.pop(session_id, None)


def launch_blocked_reason(settings: Settings) -> str | None:
    """Production stays closed unless it is an explicit sandbox demo."""

    if settings.environment != "production":
        return None
    if not settings.public_demo:
        return "Interactive demo sessions are not enabled on this deployment."
    blocked: list[str] = []
    if settings.email_mode != "sandbox" or settings.email_live_enabled:
        blocked.append("live email")
    if settings.campaign_live_enabled:
        blocked.append("live campaigns")
    if settings.whatsapp_live_enabled:
        blocked.append("live WhatsApp")
    if settings.n8n_lead_webhook_url.strip():
        blocked.append("an n8n webhook")
    if settings.llm_provider != "double" or settings.llm_api_key.strip():
        blocked.append("a paid chat model")
    if settings.embedding_provider != "double" or settings.embedding_api_key.strip():
        blocked.append("paid embeddings")
    if settings.billing_provider != "sandbox" or settings.stripe_secret_key.strip():
        blocked.append("a payment provider")
    if settings.google_calendar_client_secret.strip():
        blocked.append("a Google Calendar client secret")
    if blocked:
        return (
            "This deployment cannot start a demo session while it has " + ", ".join(blocked) + "."
        )
    return None


def _trim(client_key: str) -> None:
    now = time.monotonic()
    kept = [stamp for stamp in _launches.get(client_key, []) if now - stamp < LAUNCH_WINDOW_SECONDS]
    if kept:
        _launches[client_key] = kept
    else:
        _launches.pop(client_key, None)
