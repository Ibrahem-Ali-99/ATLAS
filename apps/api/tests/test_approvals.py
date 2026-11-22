import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.approvals.service import (
    create_approval,
    decide,
    execute_approved,
    execute_decisions,
)
from app.domains.crm.models import Lead
from app.domains.crm.service import create_inquiry
from app.domains.identity.models import MembershipRole, Organization
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _csrf(payload: dict[str, object]) -> dict[str, str]:
    return {"X-CSRF-Token": str(payload["csrf_token"])}


def _proposal() -> dict[str, object]:
    return {
        "title": "Bonded storage inquiry",
        "status": "qualified",
        "company_id": None,
        "contact_id": None,
        "source": "agent",
        "notes": "Rates for bonded storage",
    }


def _pending(db: Session) -> Approval:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    inquiry = create_inquiry(db, atlas.id, {"subject": "Rates", "body": "Bonded storage"})
    run = AgentRun(
        organization_id=atlas.id,
        inquiry_id=inquiry.id,
        started_by=admin.id,
        status=RunStatus.awaiting_approval,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return create_approval(
        db,
        organization_id=atlas.id,
        run_id=run.id,
        requested_by=admin.id,
        action_type=ActionType.create_lead,
        payload=_proposal(),
        position=0,
    )


def test_rejected_and_pending_approvals_do_not_write(client: TestClient, db: Session) -> None:
    approval = _pending(db)
    ada = login(client, "ada@example.com", PASSWORD)
    rejected = client.post(
        f"/api/v1/organizations/{approval.organization_id}/approvals/{approval.id}/reject",
        json={},
        headers=_csrf(ada),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    db.rollback()
    executed, rejected_count, failed = execute_decisions(
        db, approval.organization_id, approval.run_id
    )
    assert (executed, rejected_count, failed) == (0, 1, 0)
    assert _lead_count(db, approval.organization_id) == 0
    with pytest.raises(AppError) as caught:
        execute_approved(db, approval.organization_id, approval.id)
    assert caught.value.code == "invalid_transition"
    assert _lead_count(db, approval.organization_id) == 0


def test_duplicate_approval_and_duplicate_execution(client: TestClient, db: Session) -> None:
    approval = _pending(db)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    path = f"/api/v1/organizations/{approval.organization_id}/approvals/{approval.id}/approve"
    first = client.post(path, json={}, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(path, json={}, headers=headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_decided"
    db.rollback()
    result = execute_approved(db, approval.organization_id, approval.id)
    assert result["lead_id"]
    with pytest.raises(AppError) as caught:
        execute_approved(db, approval.organization_id, approval.id)
    assert caught.value.code == "already_executed"
    assert _lead_count(db, approval.organization_id) == 1


def test_modified_payload_is_invalid_and_writes_nothing(client: TestClient, db: Session) -> None:
    approval = _pending(db)
    approval.payload = {**approval.payload, "title": "Changed title"}
    db.commit()
    ada = login(client, "ada@example.com", PASSWORD)
    response = client.post(
        f"/api/v1/organizations/{approval.organization_id}/approvals/{approval.id}/approve",
        json={},
        headers=_csrf(ada),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "approval_invalid"
    db.expire_all()
    stored = db.get(Approval, approval.id)
    assert stored is not None
    assert stored.status == ApprovalStatus.failed
    assert _lead_count(db, approval.organization_id) == 0


def test_expired_approval_cannot_be_decided(client: TestClient, db: Session) -> None:
    approval = _pending(db)
    approval.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    ada = login(client, "ada@example.com", PASSWORD)
    response = client.post(
        f"/api/v1/organizations/{approval.organization_id}/approvals/{approval.id}/approve",
        json={},
        headers=_csrf(ada),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "approval_expired"
    db.expire_all()
    stored = db.get(Approval, approval.id)
    assert stored is not None
    assert stored.status == ApprovalStatus.expired
    assert _lead_count(db, approval.organization_id) == 0


def test_approved_payload_change_blocks_execution(db: Session) -> None:
    approval = _pending(db)
    decide(
        db,
        approval.organization_id,
        approval.id,
        approval.requested_by,
        approved=True,
        note=None,
    )
    approval.payload = {**approval.payload, "title": "Changed after approval"}
    db.commit()
    with pytest.raises(AppError) as caught:
        execute_approved(db, approval.organization_id, approval.id)
    assert caught.value.code == "approval_invalid"
    assert _lead_count(db, approval.organization_id) == 0


def test_staff_csrf_and_tenant_cannot_approve(client: TestClient, db: Session) -> None:
    approval = _pending(db)
    staff = make_user(db, "sam@example.com")
    outsider = make_user(db, "outsider@example.org")
    northwind = make_organization(db, "Northwind", "northwind")
    organization_id = approval.organization_id
    atlas_org = db.get(Organization, organization_id)
    assert atlas_org is not None
    make_membership(db, staff, atlas_org, MembershipRole.staff)
    make_membership(db, outsider, northwind, MembershipRole.admin)

    sam = login(client, "sam@example.com", PASSWORD)
    forbidden = client.post(
        f"/api/v1/organizations/{organization_id}/approvals/{approval.id}/approve",
        json={},
        headers=_csrf(sam),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"

    login(client, "ada@example.com", PASSWORD)
    missing_csrf = client.post(
        f"/api/v1/organizations/{organization_id}/approvals/{approval.id}/approve",
        json={},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "csrf_failed"

    other = login(client, "outsider@example.org", PASSWORD)
    hidden = client.post(
        f"/api/v1/organizations/{organization_id}/approvals/{approval.id}/approve",
        json={},
        headers=_csrf(other),
    )
    assert hidden.status_code == 404
    db.expire_all()
    stored = db.get(Approval, approval.id)
    assert stored is not None
    assert stored.status == ApprovalStatus.pending
    assert _lead_count(db, organization_id) == 0


def test_resume_of_unknown_run_is_not_found(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    response = client.post(
        f"/api/v1/organizations/{atlas.id}/agent-runs/{uuid.uuid4()}/resume",
        headers=_csrf(ada),
    )
    assert response.status_code == 404


def _lead_count(db: Session, organization_id: uuid.UUID) -> int:
    total = db.scalar(
        select(func.count()).select_from(Lead).where(Lead.organization_id == organization_id)
    )
    return int(total or 0)
