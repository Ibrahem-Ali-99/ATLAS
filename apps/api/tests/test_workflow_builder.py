import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.automation.models import WorkflowTask
from app.domains.automation.workflows import dispatch_workflow, recover_workflows
from app.domains.crm.service import create_lead
from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_manual_workflow_conditions_and_approval_survive_a_restart(
    client: TestClient, db: Session
) -> None:
    org = make_organization(db, "Workflow Workspace", "workflow-builder")
    other = make_organization(db, "Other Workspace", "other-workflow-workspace")
    admin = make_user(db, "workflow-builder@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    make_membership(db, admin, other, MembershipRole.admin)
    lead = create_lead(db, org.id, admin.id, {"title": "Qualified request", "status": "qualified"})
    foreign = create_lead(db, other.id, admin.id, {"title": "Private lead", "status": "new"})
    unmatched = create_lead(db, org.id, admin.id, {"title": "New request", "status": "new"})
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/workflow-definitions"
    definition = {
        "name": "Follow through",
        "slug": "follow-through",
        "definition": {
            "trigger": "lead_created",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "qualified"}],
            "actions": [
                {"type": "require_approval"},
                {"type": "create_task", "title": "Follow up"},
            ],
        },
    }
    created = client.post(path, json=definition, headers=headers)
    assert created.status_code == 201, created.text
    url = f"{path}/{created.json()['id']}"

    def queue(lead_id: uuid.UUID, request_id: uuid.UUID):
        return client.post(
            f"{url}/runs",
            headers=headers,
            json={"request_id": str(request_id), "lead_id": str(lead_id)},
        )

    assert queue(foreign.id, uuid.uuid4()).status_code == 404
    skipped = queue(unmatched.id, uuid.uuid4())
    assert skipped.status_code == 202, skipped.text
    dispatch_workflow(db, org.id, uuid.UUID(skipped.json()["id"]))
    assert client.get(f"{url}/runs").json()[0]["status"] == "skipped"

    request_id = uuid.uuid4()
    pending = queue(lead.id, request_id)
    assert pending.status_code == 202, pending.text
    run_id = pending.json()["id"]
    assert queue(lead.id, request_id).json()["id"] == run_id
    assert queue(unmatched.id, request_id).status_code == 409
    dispatch_workflow(db, org.id, uuid.UUID(run_id))
    recover_workflows(db)
    assert client.get(f"{url}/runs").json()[0]["status"] == "awaiting_approval"
    reviews = client.get(f"{path}/reviews").json()
    assert [review["id"] for review in reviews] == [run_id]
    assert client.get(path.replace(str(org.id), str(other.id)) + "/reviews").json() == []
    assert db.scalar(select(WorkflowTask).where(WorkflowTask.lead_id == lead.id)) is None
    assert (
        client.post(
            f"{url}/runs/{run_id}/review", headers=headers, json={"decision": "approve"}
        ).status_code
        == 200
    )
    dispatch_workflow(db, org.id, uuid.UUID(run_id))
    assert db.scalar(select(WorkflowTask).where(WorkflowTask.lead_id == lead.id)) is not None
    assert client.get(f"{url}/runs").json()[0]["status"] == "completed"
    assert client.get(f"{path}/reviews").json() == []
    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(path).json()[0]["archived_at"]
    assert client.get(f"{url}/runs").json()[0]["id"] == run_id
    assert queue(lead.id, uuid.uuid4()).status_code == 409


def test_any_conditions_choose_one_path_and_keep_reordered_steps(
    client: TestClient, db: Session
) -> None:
    org = make_organization(db, "Workflow branches", "workflow-branches")
    admin = make_user(db, "workflow-branches@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/workflow-definitions"
    root = path.rsplit("/", 1)[0]
    progress = f"{root}/onboarding/progress"
    assert client.get(progress).json() == dict.fromkeys(
        ("profile", "company", "contact", "lead", "inquiry", "knowledge", "assistant", "workflow"),
        False,
    )
    assert (
        client.patch(
            f"{root}/onboarding",
            json={"name": "Workflow branches", "completed": True},
            headers=headers,
        ).status_code
        == 200
    )
    company = client.post(f"{root}/companies", json={"name": "First customer"}, headers=headers)
    assert company.status_code == 201, company.text
    contact = client.post(
        f"{root}/contacts",
        json={"full_name": "Customer contact", "company_id": company.json()["id"]},
        headers=headers,
    )
    assert contact.status_code == 201, contact.text
    assert client.get(progress).json()["lead"] is False
    graph = {
        "trigger": "lead_created",
        "condition_mode": "any",
        "conditions": [
            {"field": "lead_status", "operator": "equals", "value": value}
            for value in ("qualified", "contacted")
        ],
        "actions": [
            {"type": "create_task", "title": "Matched", "priority": "urgent", "due_in_hours": 2}
        ],
        "otherwise_actions": [
            {"type": "require_approval"},
            {"type": "create_task", "title": "Review later"},
            {"type": "update_lead", "status": "contacted"},
        ],
    }
    response = client.post(
        path,
        json={"name": "Route leads", "slug": "route-leads", "definition": graph},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    url = f"{path}/{response.json()['id']}"
    graph["otherwise_actions"][1:] = graph["otherwise_actions"][:0:-1]
    edited = client.patch(
        url,
        json={"name": "Route leads", "slug": "route-leads", "definition": graph},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["definition"]["otherwise_actions"][1]["type"] == "update_lead"
    for status, title in (("contacted", "Matched"), ("new", "Review later")):
        new_lead = client.post(
            f"{root}/leads",
            json={"title": title, "status": status, "contact_id": contact.json()["id"]},
            headers=headers,
        )
        assert new_lead.status_code == 201, new_lead.text
        lead_id = uuid.UUID(new_lead.json()["id"])
        if status == "contacted":
            inquiry = client.post(
                f"{root}/inquiries",
                json={
                    "subject": "First request",
                    "body": "Review the service",
                    "lead_id": str(lead_id),
                },
                headers=headers,
            )
            assert inquiry.status_code == 201, inquiry.text
        queued = client.post(
            f"{url}/runs",
            json={"lead_id": str(lead_id), "request_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert queued.status_code == 202, queued.text
        run_id = queued.json()["id"]
        dispatch_workflow(db, org.id, uuid.UUID(run_id))
        if status == "new":
            assert db.scalar(select(WorkflowTask).where(WorkflowTask.lead_id == lead_id)) is None
            recover_workflows(db)
            assert (
                client.post(
                    f"{url}/runs/{run_id}/review",
                    headers=headers,
                    json={"decision": "approve"},
                ).status_code
                == 200
            )
            dispatch_workflow(db, org.id, uuid.UUID(run_id))
            assert client.get(f"{root}/leads/{lead_id}").json()["status"] == "contacted"
        tasks = db.scalars(select(WorkflowTask).where(WorkflowTask.lead_id == lead_id)).all()
        assert [task.title for task in tasks] == [title]
        if status == "contacted":
            assert tasks[0].priority == "urgent" and tasks[0].due_at is not None
    assert client.get(progress).json() == {
        "profile": True,
        "company": True,
        "contact": True,
        "lead": True,
        "inquiry": True,
        "workflow": True,
        "knowledge": False,
        "assistant": False,
    }


def test_preview_does_not_save_and_a_repeat_needs_confirmation(
    client: TestClient, db: Session
) -> None:
    org = make_organization(db, "Workflow Preview", "workflow-preview")
    admin = make_user(db, "workflow-preview@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    lead = create_lead(db, org.id, admin.id, {"title": "Preview lead", "status": "new"})
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/workflow-definitions"
    created = client.post(
        path,
        headers=headers,
        json={
            "name": "Task preview",
            "slug": "task-preview",
            "definition": {
                "trigger": "lead_created",
                "actions": [{"type": "create_task", "title": "Preview follow-up"}],
            },
        },
    )
    assert created.status_code == 201, created.text
    url = f"{path}/{created.json()['id']}"

    def queue(**extra: object):
        return client.post(
            f"{url}/runs",
            headers=headers,
            json={"request_id": str(uuid.uuid4()), "lead_id": str(lead.id), **extra},
        )

    preview = queue(dry_run=True)
    assert preview.status_code == 202, preview.text
    dispatch_workflow(db, org.id, uuid.UUID(preview.json()["id"]))
    inspected = client.get(f"{url}/runs").json()[0]
    assert inspected["status"] == "simulated"
    assert inspected["dry_run"] is True
    assert db.scalar(select(WorkflowTask).where(WorkflowTask.lead_id == lead.id)) is None
    applied = queue()
    assert applied.status_code == 202, applied.text
    dispatch_workflow(db, org.id, uuid.UUID(applied.json()["id"]))
    tasks = db.scalars(select(WorkflowTask).where(WorkflowTask.lead_id == lead.id)).all()
    assert len(tasks) == 1
    repeated = queue()
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "workflow_effect_already_recorded"
    confirmed = queue(confirm_repeat=True)
    assert confirmed.status_code == 202, confirmed.text
    dispatch_workflow(db, org.id, uuid.UUID(confirmed.json()["id"]))
    tasks = db.scalars(select(WorkflowTask).where(WorkflowTask.lead_id == lead.id)).all()
    assert len(tasks) == 2
    refused = client.post(f"{url}/runs/{applied.json()['id']}/retry", headers=headers)
    assert refused.status_code == 409


def test_a_second_run_waits_until_the_first_finishes(client: TestClient, db: Session) -> None:
    org = make_organization(db, "Workflow In Progress", "workflow-in-progress")
    admin = make_user(db, "workflow-in-progress@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    lead = create_lead(
        db, org.id, admin.id, {"title": "North pier expansion", "status": "qualified"}
    )
    headers = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{org.id}/workflow-definitions"
    created = client.post(
        path,
        headers=headers,
        json={
            "name": "Qualified lead follow-up branch",
            "slug": "qualified-lead-follow-up-branch",
            "definition": {
                "trigger": "lead_created",
                "conditions": [
                    {"field": "lead_status", "operator": "equals", "value": "qualified"}
                ],
                "actions": [
                    {"type": "require_approval", "note": "Confirm the bonded service sheet"},
                    {"type": "create_task", "title": "Send the bonded service sheet"},
                ],
                "otherwise_actions": [
                    {"type": "create_task", "title": "Ask Mina for the missing yard details"}
                ],
            },
        },
    )
    assert created.status_code == 201, created.text
    url = f"{path}/{created.json()['id']}"

    def queue(**extra: object):
        return client.post(
            f"{url}/runs",
            headers=headers,
            json={"request_id": str(uuid.uuid4()), "lead_id": str(lead.id), **extra},
        )

    started = queue()
    assert started.status_code == 202, started.text
    while_pending = queue()
    assert while_pending.status_code == 409
    assert while_pending.json()["error"]["code"] == "workflow_run_in_progress"
    confirmed_early = queue(confirm_repeat=True)
    assert confirmed_early.status_code == 409
    assert confirmed_early.json()["error"]["code"] == "workflow_run_in_progress"
    preview = queue(dry_run=True)
    assert preview.status_code == 202, preview.text
    dispatch_workflow(db, org.id, uuid.UUID(started.json()["id"]))
    waiting = queue()
    assert waiting.status_code == 409
    assert waiting.json()["error"]["code"] == "workflow_run_in_progress"
    assert (
        client.post(
            f"{url}/runs/{started.json()['id']}/review",
            headers=headers,
            json={"decision": "approve"},
        ).status_code
        == 200
    )
    dispatch_workflow(db, org.id, uuid.UUID(started.json()["id"]))
    assert db.scalar(select(WorkflowTask).where(WorkflowTask.lead_id == lead.id)) is not None
    repeated = queue()
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "workflow_effect_already_recorded"
    confirmed = queue(confirm_repeat=True)
    assert confirmed.status_code == 202, confirmed.text
