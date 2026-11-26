from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.monitoring.service import diagnostics
from app.domains.observability.models import WorkerHeartbeat
from app.domains.provenance.origin import DataScope
from tests.factories import make_organization


def _beat(
    db: Session,
    worker_id: str,
    kind: str,
    *,
    status: str,
    age: timedelta,
    error: str | None = None,
) -> None:
    moment = datetime.now(UTC) - age
    db.add(
        WorkerHeartbeat(
            worker_id=worker_id,
            worker_kind=kind,
            status=status,
            started_at=moment,
            heartbeat_at=moment,
            last_error_code=error,
            processed_count=0,
        )
    )
    db.commit()


def test_replaced_workers_are_not_current_failures(db: Session) -> None:
    organization = make_organization(db, "Worker Health", "worker-health")
    kind = "knowledge-health"
    _beat(db, "knowledge-old", kind, status="idle", age=timedelta(hours=3))
    _beat(
        db,
        "knowledge-failed",
        kind,
        status="error",
        age=timedelta(minutes=20),
        error="ingestion_failed",
    )
    _beat(db, "knowledge-live", kind, status="idle", age=timedelta(seconds=5))

    body = diagnostics(db, organization.id, DataScope.operational)
    knowledge = [item for item in body["workers"] if item["kind"] == kind]
    current = next(item for item in knowledge if item["generation"] == "current")
    previous = [item for item in knowledge if item["generation"] == "previous"]

    assert current["id"] == "knowledge-live"
    assert current["status"] == "idle"
    assert {item["status"] for item in previous} == {"replaced"}
    recorded = next(item for item in previous if item["id"] == "knowledge-failed")
    assert recorded["last_error_code"] == "ingestion_failed"
    assert "stalled" not in {item["status"] for item in knowledge}


def test_a_fresh_worker_error_stays_visible(db: Session) -> None:
    organization = make_organization(db, "Worker Error", "worker-error")
    _beat(
        db,
        "automation-live",
        "automation-error",
        status="error",
        age=timedelta(seconds=2),
        error="TimeoutError",
    )
    body = diagnostics(db, organization.id)
    current = next(item for item in body["workers"] if item["id"] == "automation-live")
    assert current["status"] == "error"
    assert current["generation"] == "current"
    assert current["last_error_code"] == "TimeoutError"


def test_a_stopped_process_is_not_marked_stalled(db: Session) -> None:
    organization = make_organization(db, "Worker Stopped", "worker-stopped")
    _beat(db, "automation-gone", "automation-stopped", status="idle", age=timedelta(minutes=10))
    body = diagnostics(db, organization.id)
    current = next(item for item in body["workers"] if item["id"] == "automation-gone")
    assert current["status"] == "stopped"
    assert current["generation"] == "current"


def test_a_visitor_workspace_omits_platform_workers(db: Session) -> None:
    organization = make_organization(db, "Harbor Guest", "harbor-visitor-health")
    _beat(
        db,
        "knowledge-secret",
        "knowledge-hidden",
        status="error",
        age=timedelta(seconds=1),
        error="ingestion_failed",
    )
    body = diagnostics(db, organization.id, include_platform=False)
    assert body["platform_visible"] is False
    assert body["workers"] == []
    assert body["slowest_steps"] == []
    assert body["duration_buckets"] == []
    assert body["cost_usd"] is None
