from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.observability.models import WorkerHeartbeat


def touch(
    db: Session,
    worker_id: str,
    worker_kind: str,
    *,
    status: str,
    success: bool = False,
    error: str | None = None,
) -> None:
    now = datetime.now(UTC)
    row = db.scalar(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))
    if row is None:
        row = WorkerHeartbeat(
            worker_id=worker_id,
            worker_kind=worker_kind,
            status=status,
            started_at=now,
            heartbeat_at=now,
        )
        db.add(row)
    row.status = status
    row.heartbeat_at = now
    row.last_error_code = error[:80] if error else None
    if success:
        row.last_success_at = now
        row.processed_count += 1
    db.commit()
