"""Origin stays on the record that created it, and analytics count that scope."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.analytics.service import snapshot
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.approvals.service import create_approval, decide, execute_approved
from app.domains.automation.models import WorkflowRun, WorkflowStatus
from app.domains.automation.workflows import complete_lead_callback, stage_lead_created
from app.domains.crm.models import Lead
from app.domains.crm.service import create_inquiry, create_lead
from app.domains.identity.models import MembershipRole
from app.domains.knowledge.service import ingest_document, mark_reindex, store_upload
from app.domains.provenance.origin import DataScope, Origin
from app.integrations.language import OpenAICompatibleChatClient, get_chat_client
from tests.ai_clients import HashEmbeddingClient
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf, _org


def test_scopes_keep_operational_demo_evaluation_and_legacy_apart(
    client: TestClient, db: Session
) -> None:
    admin = make_user(db, "origin-admin@example.com")
    staff = make_user(db, "origin-staff@example.com")
    outsider = make_user(db, "origin-out@example.com")
    atlas = make_organization(db, "Origin Atlas", "origin-atlas")
    other = make_organization(db, "Origin Other", "origin-other")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, staff, atlas, MembershipRole.staff)
    make_membership(db, outsider, other, MembershipRole.admin)
    ada = login(client, "origin-admin@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)

    operational = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Operational pier", "status": "new", "origin": "operational"},
        headers=headers,
    )
    demo = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Demo pier", "status": "won", "origin": "demo"},
        headers=headers,
    )
    assert operational.status_code == 201, operational.text
    assert demo.status_code == 201, demo.text
    operational_id = operational.json()["id"]
    assert operational.json()["origin"] == "operational"
    assert demo.json()["origin"] == "demo"

    legacy = Lead(
        organization_id=atlas.id,
        owner_user_id=admin.id,
        title="Legacy pier",
        status="new",
    )
    db.add(legacy)
    db.commit()
    db.refresh(legacy)
    assert legacy.origin == Origin.unknown

    default = client.get(f"/api/v1/organizations/{org}/analytics")
    assert default.status_code == 200
    body = default.json()
    assert body["scope"] == "operational"
    assert body["leads_total"] == 1
    assert body["conversion"]["denominator"] == 0
    assert "synthetic" not in body["provenance_notice"].lower()
    assert body["lead_origins"] == {"operational": 1, "demo": 1, "evaluation": 0, "unknown": 1}
    demo_view = client.get(f"/api/v1/organizations/{org}/analytics?scope=demo")
    assert demo_view.json()["leads_total"] == 1
    assert demo_view.json()["conversion"]["won"] == 1
    legacy_view = client.get(f"/api/v1/organizations/{org}/analytics?scope=unknown")
    assert legacy_view.json()["leads_total"] == 1
    everything = client.get(f"/api/v1/organizations/{org}/analytics?scope=all")
    assert everything.json()["leads_total"] == 3
    counted = snapshot(db, atlas.id, DataScope.operational)
    direct = db.scalar(
        select(func.count())
        .select_from(Lead)
        .where(Lead.organization_id == atlas.id, Lead.origin == Origin.operational)
    )
    assert counted["leads_total"] == int(direct or 0) == 1

    listed = client.get(f"/api/v1/organizations/{org}/leads?origin=demo", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [demo.json()["id"]]
    changed = client.patch(
        f"/api/v1/organizations/{org}/leads/{operational_id}",
        json={"notes": "still operational", "origin": "demo"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["origin"] == "operational"
    assert changed.json()["notes"] == "still operational"

    inquiry = create_inquiry(
        db,
        atlas.id,
        {"subject": "Evaluation yard", "body": "Count the pallets.", "origin": Origin.evaluation},
    )
    assert inquiry.origin == Origin.evaluation
    empty = get_settings().model_copy(update={"llm_api_key": ""})
    client.app.dependency_overrides[get_chat_client] = lambda: OpenAICompatibleChatClient(empty)
    try:
        started = client.post(
            f"/api/v1/organizations/{org}/agent-runs",
            json={"inquiry_id": str(inquiry.id)},
            headers=headers,
        )
    finally:
        client.app.dependency_overrides.pop(get_chat_client, None)
    assert started.status_code == 503
    evaluation_runs = client.get(f"/api/v1/organizations/{org}/agent-runs?scope=evaluation")
    assert evaluation_runs.json()["total"] == 1
    assert evaluation_runs.json()["items"][0]["origin"] == "evaluation"
    hidden = client.get(f"/api/v1/organizations/{org}/agent-runs")
    assert hidden.json()["total"] == 0
    run = db.get(AgentRun, uuid.UUID(evaluation_runs.json()["items"][0]["id"]))
    assert run is not None
    approval = create_approval(
        db,
        organization_id=atlas.id,
        run_id=run.id,
        requested_by=admin.id,
        action_type=ActionType.create_lead,
        payload={"title": "Evaluation lead", "status": "new", "notes": "from the run"},
        position=0,
    )
    assert approval.origin == Origin.evaluation
    decide(db, atlas.id, approval.id, admin.id, approved=True, note=None)
    execute_approved(db, atlas.id, approval.id)
    created = db.scalar(select(Lead).where(Lead.title == "Evaluation lead"))
    assert created is not None
    assert created.origin == Origin.evaluation
    assert snapshot(db, atlas.id)["leads_total"] == 1

    kept = create_lead(db, atlas.id, admin.id, {"title": "Keep operational", "status": "qualified"})
    update_run = AgentRun(
        organization_id=atlas.id,
        inquiry_id=inquiry.id,
        started_by=admin.id,
        status=RunStatus.awaiting_approval,
        origin=Origin.evaluation,
    )
    db.add(update_run)
    db.commit()
    db.refresh(update_run)
    update = create_approval(
        db,
        organization_id=atlas.id,
        run_id=update_run.id,
        requested_by=admin.id,
        action_type=ActionType.update_lead,
        payload={"lead_id": str(kept.id), "status": "qualified", "notes": "approved note"},
        position=0,
    )
    decide(db, atlas.id, update.id, admin.id, approved=True, note=None)
    execute_approved(db, atlas.id, update.id)
    db.refresh(kept)
    assert kept.origin == Origin.operational
    assert kept.notes == "approved note"

    demo_lead = db.get(Lead, uuid.UUID(demo.json()["id"]))
    assert demo_lead is not None
    stage_lead_created(db, atlas.id, demo_lead.id, None)
    db.commit()
    workflow = db.scalar(select(WorkflowRun).where(WorkflowRun.lead_id == demo_lead.id))
    assert workflow is not None
    assert workflow.origin == Origin.demo
    workflow.status = WorkflowStatus.accepted
    db.commit()
    complete_lead_callback(db, atlas.id, workflow.id, demo_lead.id)
    db.refresh(demo_lead)
    db.refresh(workflow)
    assert demo_lead.origin == Origin.demo
    assert workflow.origin == Origin.demo
    assert workflow.status == WorkflowStatus.completed

    document = store_upload(
        db,
        atlas.id,
        admin.id,
        filename="yard.txt",
        media_type="text/plain",
        payload=b"The yard stores 42 pallets.",
        origin=Origin.demo,
    )
    mark_reindex(db, atlas.id, document.id)
    ingest_document(document.id, HashEmbeddingClient())
    db.refresh(document)
    assert document.origin == Origin.demo
    assert document.status.value == "ready"

    staff_session = login(client, "origin-staff@example.com", PASSWORD)
    staff_lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "Staff operational", "status": "new"},
        headers=_csrf(staff_session),
    )
    assert staff_lead.status_code == 201
    assert staff_lead.json()["origin"] == "operational"
    denied = client.post(
        f"/api/v1/organizations/{org}/approvals/{approval.id}/approve",
        json={},
        headers=_csrf(staff_session),
    )
    assert denied.status_code == 403
    stored_approval = db.get(Approval, approval.id)
    assert stored_approval is not None
    assert stored_approval.status == ApprovalStatus.executed

    outsider_session = login(client, "origin-out@example.com", PASSWORD)
    foreign = client.get(f"/api/v1/organizations/{_org(outsider_session)}/analytics")
    assert foreign.json()["leads_total"] == 0
    missing = client.get(f"/api/v1/organizations/{_org(outsider_session)}/leads/{operational_id}")
    assert missing.status_code == 404
    blocked = client.get(f"/api/v1/organizations/{org}/leads/{operational_id}")
    assert blocked.status_code == 404
    admin_again = login(client, "origin-admin@example.com", PASSWORD)
    visible = client.get(
        f"/api/v1/organizations/{org}/leads/{legacy.id}", headers=_csrf(admin_again)
    )
    assert visible.status_code == 200
    assert visible.json()["origin"] == "unknown"
