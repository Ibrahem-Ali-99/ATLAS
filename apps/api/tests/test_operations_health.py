import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.automation.models import WorkflowKind, WorkflowRun, WorkflowStatus
from app.domains.identity.models import MembershipRole
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.knowledge.models import Document, DocumentStatus
from app.domains.monitoring.service import diagnostics
from app.domains.observability.models import OperationTrace, WorkerHeartbeat
from app.domains.provenance.origin import DataScope, Origin
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def test_current_assistant_health_ignores_an_older_failure(db: Session) -> None:
    organization = make_organization(db, "Harbor Health", "harbor-health")
    now = datetime.now(UTC)
    db.add_all(
        [
            OperationTrace(
                organization_id=organization.id,
                operation="assistant_response",
                status="failed",
                error_code="llm_failed",
                started_at=now - timedelta(days=3),
            ),
            OperationTrace(
                organization_id=organization.id,
                operation="assistant_response",
                status="succeeded",
                started_at=now - timedelta(minutes=5),
            ),
        ]
    )
    db.commit()

    body = diagnostics(db, organization.id, DataScope.all)
    assistant = body["activity"]["assistant"]
    assert assistant["status"] == "available"
    assert assistant["recent_replies"] == 1
    assert assistant["recent_errors"] == 0
    assert assistant["earlier_errors"] == 1
    assert body["activity"]["notice"].startswith("Current health is the latest stored state.")


def test_the_latest_assistant_failure_is_current_health(db: Session) -> None:
    organization = make_organization(db, "Harbor Errors", "harbor-errors")
    now = datetime.now(UTC)
    db.add(
        OperationTrace(
            organization_id=organization.id,
            operation="assistant_response",
            status="failed",
            error_code="llm_failed",
            started_at=now - timedelta(minutes=2),
        )
    )
    db.commit()

    assistant = diagnostics(db, organization.id)["activity"]["assistant"]
    assert assistant["status"] == "errors"
    assert assistant["recent_errors"] == 1
    assert assistant["last_error_code"] == "llm_failed"
    assert assistant["earlier_errors"] == 0


def test_demonstration_workflow_counts_appear_only_in_all_records(db: Session) -> None:
    organization = make_organization(db, "Harbor Runs", "harbor-runs")
    user = make_user(db, "harbor-runs@example.com")
    db.add(
        Document(
            organization_id=organization.id,
            uploaded_by=user.id,
            title="Bonded note",
            filename="bonded.txt",
            media_type="text/plain",
            byte_size=20,
            storage_path="harbor/bonded.txt",
            status=DocumentStatus.ready,
            origin=Origin.demo,
        )
    )
    db.add(
        WorkflowRun(
            organization_id=organization.id,
            kind=WorkflowKind.follow_up,
            status=WorkflowStatus.completed,
            idempotency_key="ab" * 32,
            payload={"summary": "Recorded demonstration run."},
            origin=Origin.demo,
        )
    )
    db.commit()

    operational = diagnostics(db, organization.id, DataScope.operational)["activity"]
    everything = diagnostics(db, organization.id, DataScope.all)["activity"]
    assert operational["workflows"]["completed"] == 0
    assert everything["workflows"]["completed"] == 1
    assert everything["knowledge"]["ready"] == 1
    assert everything["assistant"]["status"] == "quiet"


def test_connection_health_uses_stored_verification_not_a_live_call(db: Session) -> None:
    organization = make_organization(db, "Harbor Connections", "harbor-connections")
    now = datetime.now(UTC)
    db.add_all(
        [
            IntegrationConfig(
                organization_id=organization.id,
                integration_type=IntegrationType.chat,
                provider="groq",
                config={},
                status=IntegrationStatus.configured,
                verified_at=now,
            ),
            IntegrationConfig(
                organization_id=organization.id,
                integration_type=IntegrationType.email,
                provider="resend",
                config={},
                status=IntegrationStatus.verification_failed,
                verification_detail="unauthorized",
            ),
        ]
    )
    db.commit()

    rows = {
        item["provider"]: item
        for item in diagnostics(db, organization.id, DataScope.all)["activity"]["integrations"]
    }
    assert rows["groq"]["health"] == "connected"
    assert rows["groq"]["verified_at"] is not None
    assert rows["groq"]["recovery"] is None
    assert rows["resend"]["health"] == "authentication_required"
    assert rows["resend"]["recovery_href"] == "/integrations"


def test_hidden_platform_diagnostics_still_return_workspace_activity(db: Session) -> None:
    organization = make_organization(db, "Harbor Staff View", "harbor-staff-view")
    db.add(
        WorkerHeartbeat(
            worker_id=f"ops-health-{uuid.uuid4()}",
            worker_kind="ops-health",
            status="error",
            started_at=datetime.now(UTC),
            heartbeat_at=datetime.now(UTC),
            last_error_code="ingestion_failed",
            processed_count=0,
        )
    )
    db.commit()

    body = diagnostics(db, organization.id, include_platform=False)
    assert body["platform_visible"] is False
    assert body["workers"] == []
    assert body["activity"]["assistant"]["status"] == "quiet"


def test_staff_cannot_read_infrastructure_diagnostics(client: TestClient, db: Session) -> None:
    organization = make_organization(db, "Harbor Staff", "harbor-staff-diag")
    staff = make_user(db, "staff-diag@example.com")
    make_membership(db, staff, organization, MembershipRole.staff)
    login(client, "staff-diag@example.com", PASSWORD)

    response = client.get(f"/api/v1/organizations/{organization.id}/diagnostics?scope=all")
    assert response.status_code == 200
    body = response.json()
    assert body["platform_visible"] is False
    assert body["workers"] == []
    assert body["slowest_steps"] == []
    assert body["activity"]["notice"]


def test_an_administrator_can_read_infrastructure_diagnostics(
    client: TestClient, db: Session
) -> None:
    organization = make_organization(db, "Harbor Admin", "harbor-admin-diag")
    admin = make_user(db, "admin-diag@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    moment = datetime.now(UTC)
    worker_id = f"ops-admin-{uuid.uuid4()}"
    db.add(
        WorkerHeartbeat(
            worker_id=worker_id,
            worker_kind="ops-admin",
            status="idle",
            started_at=moment,
            heartbeat_at=moment,
            processed_count=1,
        )
    )
    db.commit()
    login(client, "admin-diag@example.com", PASSWORD)

    response = client.get(f"/api/v1/organizations/{organization.id}/diagnostics?scope=all")
    assert response.status_code == 200
    body = response.json()
    assert body["platform_visible"] is True
    assert any(item["id"] == worker_id for item in body["workers"])
    assert body["activity"]["integrations"] == []
