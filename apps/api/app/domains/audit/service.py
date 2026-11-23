import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.domains.audit.models import AuditEvent


def record_event(
    db: Session,
    organization_id: uuid.UUID,
    action: str,
    metadata: dict[str, Any],
    *,
    actor_id: uuid.UUID | None = None,
) -> AuditEvent:
    forbidden = {"secret", "credentials", "api_key", "token", "password"}

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: redact(item) for key, item in value.items() if key.lower() not in forbidden
            }
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    safe_metadata = redact(metadata)
    event = AuditEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        details=safe_metadata,
    )
    db.add(event)
    db.flush()
    return event
