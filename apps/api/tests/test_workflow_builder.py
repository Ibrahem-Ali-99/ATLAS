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
