from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.models import Document, DocumentStatus, IngestionJob, IngestionJobStatus
from app.domains.knowledge.service import claim_ingestion_job, mark_reindex, run_ingestion_job
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _org


def _job(db: Session, suffix: str = "one") -> IngestionJob:
    user = make_user(db, f"jobs-{suffix}@example.com")
    organization = make_organization(db, f"Jobs {suffix}", f"jobs-{suffix}")
    make_membership(db, user, organization, MembershipRole.admin)
    document = Document(
        organization_id=organization.id,
        uploaded_by=user.id,
        title="Queued document",
        filename="queued.txt",
        media_type="text/plain",
        byte_size=10,
        storage_path="",
        status=DocumentStatus.pending,
    )
    db.add(document)
    db.flush()
    job = IngestionJob(
        organization_id=organization.id,
        document_id=document.id,
        idempotency_key=f"document:{document.id}:v1",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_claim_is_single_owner(db: Session) -> None:
    job = _job(db)
    first = claim_ingestion_job("worker-a")
    second = claim_ingestion_job("worker-b")

    assert first is not None and first.id == job.id
    assert second is None


def test_expired_lease_can_be_reclaimed(db: Session) -> None:
    job = _job(db, "expired")
    job.status = IngestionJobStatus.running
    job.lease_owner = "dead-worker"
    job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    reclaimed = claim_ingestion_job("replacement")

    assert reclaimed is not None and reclaimed.id == job.id
    assert reclaimed.lease_owner == "replacement"


def test_stale_worker_cannot_finalize_job(db: Session, monkeypatch: MonkeyPatch) -> None:
    job = _job(db, "stale")
    claimed = claim_ingestion_job("live-worker", lease_seconds=60)
    assert claimed is not None

    current = db.scalar(select(IngestionJob).where(IngestionJob.id == job.id))
    assert current is not None
    current.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(
        "app.domains.knowledge.service.ingest_document", lambda *args, **kwargs: None
    )

    run_ingestion_job(claimed, "live-worker")

    with SessionLocal() as check:
        stored = check.get(IngestionJob, job.id)
        assert stored is not None
        assert stored.status == IngestionJobStatus.running
        assert stored.lease_owner == "live-worker"


def test_document_delete_cascades_its_job(db: Session) -> None:
    job = _job(db, "deleted")
    job_id = job.id
    document = db.get(Document, job.document_id)
    assert document is not None
    db.delete(document)
    db.commit()
    db.expire_all()

    assert db.get(IngestionJob, job_id) is None


def test_reindex_is_idempotent_for_job(db: Session) -> None:
    job = _job(db, "reindex")
    document = db.get(Document, job.document_id)
    assert document is not None

    mark_reindex(db, job.organization_id, document.id)
    mark_reindex(db, job.organization_id, document.id)

    assert db.query(IngestionJob).filter(IngestionJob.document_id == document.id).count() == 1


def test_retry_exhaustion_records_terminal_failure(db: Session, monkeypatch: MonkeyPatch) -> None:
    job = _job(db, "retry")
    job.max_attempts = 1
    db.commit()
    claimed = claim_ingestion_job("retry-worker")
    assert claimed is not None
    monkeypatch.setattr(
        "app.domains.knowledge.service.ingest_document", lambda *args, **kwargs: None
    )
    document = db.get(Document, job.document_id)
    assert document is not None
    document.status = DocumentStatus.failed
    document.error_message = "provider unavailable"
    db.commit()

    run_ingestion_job(claimed, "retry-worker")

    db.expire_all()
    stored = db.get(IngestionJob, job.id)
    assert stored is not None
    assert stored.status == IngestionJobStatus.failed
    assert stored.attempts == 1


def test_job_status_is_tenant_scoped(client: TestClient, db: Session) -> None:
    job = _job(db, "tenant")
    outsider = make_user(db, "jobs-outsider@example.com", PASSWORD)
    other = make_organization(db, "Other jobs", "jobs-other")
    make_membership(db, outsider, other, MembershipRole.admin)
    session = login(client, "jobs-outsider@example.com", PASSWORD)

    response = client.get(
        f"/api/v1/organizations/{job.organization_id}/documents/{job.document_id}/job"
    )

    assert response.status_code == 404
    assert _org(session) != str(job.organization_id)
