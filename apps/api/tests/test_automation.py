import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.approvals.service import (
    create_approval,
    decide,
    execute_approved,
    execute_decisions,
)
from app.domains.automation.hooks import create_webhook_key
from app.domains.automation.intents import recover_intents, stage_intent
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    ExecutionIntent,
    IntentStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTask,
)
from app.domains.automation.signatures import open_webhook_secret, sign_webhook
from app.domains.automation.worker import run_once
from app.domains.automation.workflows import (
    complete_lead_callback,
    dispatch_workflow,
    recover_workflows,
    stage_lead_created,
)
from app.domains.crm.models import Lead, LeadStatus
from app.domains.crm.service import create_company, create_contact, create_inquiry, create_lead
from app.domains.identity.models import MembershipRole, Organization, User
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.smtp_sink import SINK, SmtpSink
from tests.test_crm import _csrf


def test_due_scheduled_workflow_dispatches_once(db: Session) -> None:
    organization = make_organization(db, "Scheduled workspace", "scheduled-workspace")
    admin = make_user(db, "scheduler@example.com")
    scheduled = WorkflowDefinition(
        organization_id=organization.id,
        created_by=admin.id,
        slug="hourly-task",
        name="Hourly task",
        active=True,
        next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        definition={
            "trigger": "schedule",
            "interval_seconds": 3600,
            "actions": [
                {"type": "create_task", "title": "Check the queue"},
            ],
        },
    )
    db.add(scheduled)
    db.commit()
    assert run_once() == 1
    assert run_once() == 0
    db.expire_all()
    assert scheduled.next_run_at is not None and scheduled.next_run_at > datetime.now(UTC)
    assert (
        db.scalar(select(WorkflowTask.title).where(WorkflowTask.organization_id == organization.id))
        == "Check the queue"
    )


def test_workflow_activation_enforces_definition_quota(client: TestClient, db: Session) -> None:
    organization = make_organization(db, "Workflow quota", "workflow-quota")
    admin = make_user(db, "workflow-quota@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    root = f"/api/v1/organizations/{organization.id}/workflow-definitions"
    draft = {"definition": {"trigger": "schedule", "actions": [{"type": "create_task"}]}}
    rows = []
    for index in range(3):
        body = {**draft, "name": f"Draft {index}", "slug": f"draft-{index}"}
        created = client.post(root, headers=headers, json=body)
        assert created.status_code == 201, created.text
        rows.append(created.json()["id"])
    duplicate = client.post(
        root, headers=headers, json={**draft, "name": "Draft 0", "slug": "draft-0"}
    )
    assert duplicate.status_code == 409
    for workflow in rows[:2]:
        assert client.post(f"{root}/{workflow}/activate", headers=headers).status_code == 200
    blocked = client.post(f"{root}/{rows[2]}/activate", headers=headers)
    assert blocked.status_code == 402
    assert client.post(f"{root}/{rows[0]}/pause", headers=headers).status_code == 200
    assert client.post(f"{root}/{rows[2]}/activate", headers=headers).status_code == 200


def test_workflow_draft_edit_activation_and_local_execution(
    client: TestClient, db: Session
) -> None:
    org = make_organization(db, "Workflow acceptance", "workflow-acceptance")
    admin = make_user(db, "workflow-admin@example.com")
    make_membership(db, admin, org, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    root = f"/api/v1/organizations/{org.id}"
    path = f"{root}/workflow-definitions"
    body = {
        "name": "New lead follow-up",
        "slug": "new-lead-follow-up",
        "definition": {
            "trigger": "schedule",
            "interval_seconds": 60,
            "actions": [{"type": "create_task"}],
        },
    }
    draft = client.post(path, json=body, headers=headers)
    assert draft.status_code == 201, draft.text
    assert draft.json()["next_run_at"] is None
    detail = f"{path}/{draft.json()['id']}"
    activated = client.post(f"{detail}/activate", headers=headers)
    assert activated.status_code == 200, activated.text
    assert activated.json()["next_run_at"] is not None
    assert client.patch(detail, json=body, headers=headers).status_code == 409
    paused = client.post(f"{detail}/pause", headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["next_run_at"] is None

    body["definition"] = {
        "trigger": "lead_created",
        "actions": [
            {"type": "update_lead", "status": "contacted"},
            {"type": "create_task", "title": "Prepare estimate"},
            {"type": "create_task", "title": "Review account"},
        ],
    }
    edited = client.patch(detail, json=body, headers=headers)
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    assert client.post(f"{detail}/activate", headers=headers).status_code == 200
    created = client.post(f"{root}/leads", json={"title": "Customer inquiry"}, headers=headers)
    assert created.status_code == 201, created.text
    lead_id = uuid.UUID(created.json()["id"])
    run = db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.lead_id == lead_id,
            WorkflowRun.payload["workflow_definition_id"].as_string() == draft.json()["id"],
        )
    )
    assert run is not None
    dispatch_workflow(db, org.id, run.id)
    dispatch_workflow(db, org.id, run.id)
    assert db.get(Lead, lead_id).status == LeadStatus.contacted
    assert run.status == WorkflowStatus.completed
    assert set(
        db.scalars(select(WorkflowTask.title).where(WorkflowTask.workflow_run_id == run.id))
    ) == {"Prepare estimate", "Review account"}


def test_restart_does_not_resend_an_uncertain_email(db: Session) -> None:
    approval = _email_approval(db)
    payload = dict(approval.payload)
    payload["lead_id"] = str(_lead(db, approval).id)
    intent = stage_intent(db, approval, payload)
    intent.status = IntentStatus.dispatching
    approval.status = ApprovalStatus.executing
    db.commit()
    before = _messages()
    recover_intents(db)
    db.expire_all()
    stored = db.get(ExecutionIntent, intent.id)
    assert stored is not None
    assert stored.status == IntentStatus.needs_attention
    assert db.get(Approval, approval.id).status == ApprovalStatus.needs_attention
    assert _messages() == before
    with pytest.raises(AppError) as exc:
        execute_approved(db, approval.organization_id, approval.id)
    assert exc.value.code == "needs_attention"
    assert _messages() == before


def test_restart_sends_a_pending_email_once(db: Session) -> None:
    approval = _email_approval(db)
    lead = _lead(db, approval)
    payload = dict(approval.payload)
    payload["lead_id"] = str(lead.id)
    stage_intent(db, approval, payload)
    approval.status = ApprovalStatus.executing
    db.commit()
    before = _messages()
    recover_intents(db)
    recover_intents(db)
    assert _messages() == before + 1
    email = db.scalar(
        select(EmailMessage).where(EmailMessage.organization_id == approval.organization_id)
    )
    assert email is not None
    assert email.status.value == "sent"
    assert email.mode == "sandbox"
    assert email.provider_message_id


def test_restart_books_a_simulated_appointment_that_never_landed(db: Session) -> None:
    approval, _shared = _appointment_approval(db)
    lead = _lead(db, approval)
    payload = dict(approval.payload)
    payload["lead_id"] = str(lead.id)
    intent = stage_intent(db, approval, payload)
    intent.status = IntentStatus.dispatching
    approval.status = ApprovalStatus.executing
    db.commit()
    recover_intents(db)
    db.expire_all()
    bookings = list(db.scalars(select(CalendarBooking)))
    assert len(bookings) == 1
    assert bookings[0].provider == "simulation"
    assert bookings[0].provider_event_id is None
    stored = db.get(Approval, approval.id)
    assert stored is not None
    assert stored.status == ApprovalStatus.executed
    before = len(bookings)
    recover_intents(db)
    bookings = list(db.scalars(select(CalendarBooking)))
    assert len(bookings) == before


def test_concurrent_email_dispatch_sends_one_message(db: Session) -> None:
    approval = _email_approval(db)
    decide(
        db, approval.organization_id, approval.id, approval.requested_by, approved=True, note=None
    )
    _lead(db, approval)
    organization_id = approval.organization_id
    approval_id = approval.id
    db.rollback()
    before = _messages()
    barrier = threading.Barrier(2)

    def attempt() -> str:
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            try:
                execute_approved(session, organization_id, approval_id)
            except AppError as exc:
                return exc.code
            return "ok"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(lambda _index: attempt(), range(2)))
    assert "ok" in results
    assert _messages() == before + 1


def test_smtp_timeout_needs_attention_and_is_not_retried(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = SmtpSink(mode="timeout")
    sink.start()
    monkeypatch.setenv("ATLAS_SMTP_PORT", str(sink.port))
    monkeypatch.setenv("ATLAS_SMTP_TIMEOUT_SECONDS", "0.3")
    get_settings.cache_clear()
    approval = _email_approval(db)
    decide(
        db, approval.organization_id, approval.id, approval.requested_by, approved=True, note=None
    )
    _lead(db, approval)
    try:
        with pytest.raises(AppError) as exc:
            execute_approved(db, approval.organization_id, approval.id)
        assert exc.value.code == "needs_attention"
        assert sink.messages == []
        with pytest.raises(AppError) as again:
            execute_approved(db, approval.organization_id, approval.id)
        assert again.value.code == "needs_attention"
        assert sink.messages == []
    finally:
        sink.stop()
        get_settings.cache_clear()


def test_rejected_and_expired_approvals_send_nothing(db: Session) -> None:
    rejected = _email_approval(db)
    decide(
        db, rejected.organization_id, rejected.id, rejected.requested_by, approved=False, note=None
    )
    before = _messages()
    executed, rejected_count, failed = execute_decisions(
        db, rejected.organization_id, rejected.run_id
    )
    assert (executed, rejected_count, failed) == (0, 1, 0)
    assert _messages() == before
    assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0

    expired = _email_approval(db, "ada-expired@example.com", "atlas-expired")
    decide(db, expired.organization_id, expired.id, expired.requested_by, approved=True, note=None)
    expired.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    with pytest.raises(AppError) as exc:
        execute_approved(db, expired.organization_id, expired.id)
    assert exc.value.code == "approval_expired"
    assert db.scalar(select(func.count()).select_from(ExecutionIntent)) == 0


def test_approval_cannot_cross_into_live_delivery(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    approval = _email_approval(db)
    assert approval.payload["delivery_mode"] == "sandbox"
    decide(
        db, approval.organization_id, approval.id, approval.requested_by, approved=True, note=None
    )
    monkeypatch.setattr(get_settings(), "email_mode", "live")
    with pytest.raises(AppError) as exc:
        execute_approved(db, approval.organization_id, approval.id)
    assert exc.value.code == "delivery_mode_changed"
    assert db.scalar(select(ExecutionIntent.id)) is None


def test_simulated_booking_and_cancellation(client: TestClient, db: Session) -> None:
    approval, shared = _appointment_approval(db)
    decide(
        db, approval.organization_id, approval.id, approval.requested_by, approved=True, note=None
    )
    _lead(db, approval)
    result = execute_approved(db, approval.organization_id, approval.id)
    assert result["provider"] == "simulation"
    booking = db.get(CalendarBooking, uuid.UUID(result["booking_id"]))
    assert booking is not None
    assert booking.provider_event_id is None
    other, _shared = _appointment_approval(db, shared, approval.payload)
    decide(db, other.organization_id, other.id, other.requested_by, approved=True, note=None)
    _lead(db, other)
    with pytest.raises(AppError) as exc:
        execute_approved(db, other.organization_id, other.id)
    assert exc.value.code == "slot_unavailable"
    ada = login(client, "ada@example.com", PASSWORD)
    calendar_url = (
        f"/api/v1/organizations/{approval.organization_id}/calendar/bookings/{booking.id}"
    )
    exported = client.get(f"{calendar_url}/export")
    assert exported.status_code == 200
    assert exported.headers["Content-Type"].startswith("text/calendar")
    assert f"UID:{booking.id}@atlas\r\n" in exported.text
    assert f"DTSTART:{booking.starts_at.astimezone(UTC):%Y%m%dT%H%M%SZ}\r\n" in exported.text
    cancelled = client.post(
        f"{calendar_url}/cancel",
        headers={"X-CSRF-Token": str(ada["csrf_token"])},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["provider"] == "simulation"
    assert client.get(f"{calendar_url}/export").status_code == 404


def test_webhook_secret_is_sealed_and_absent_from_reads(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    key, secret = create_webhook_key(db, atlas.id)
    assert key.secret.startswith("enc:v2:")
    assert secret not in key.secret
    assert open_webhook_secret(key.secret) == secret
    ada = login(client, "ada@example.com", PASSWORD)
    snapshot = client.get(f"/api/v1/organizations/{atlas.id}/automations")
    assert snapshot.status_code == 200
    assert secret not in snapshot.text
    listed = client.get(
        f"/api/v1/organizations/{atlas.id}/integrations/webhook-keys",
        headers={"X-CSRF-Token": str(ada["csrf_token"])},
    )
    assert listed.status_code == 200
    assert listed.json()["id"] == str(key.id)
    assert secret not in listed.text


def test_missing_callback_waits_until_the_callback_arrives(db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    lead = create_lead(db, atlas.id, admin.id, {"title": "Harbor", "status": "new"})
    create_webhook_key(db, atlas.id)
    stage_lead_created(db, atlas.id, lead.id, None)
    db.commit()
    run = db.scalar(select(WorkflowRun))
    assert run is not None
    run.status = WorkflowStatus.accepted
    db.commit()
    recover_workflows(db)
    db.expire_all()
    waiting = db.get(WorkflowRun, run.id)
    assert waiting is not None
    assert waiting.status == WorkflowStatus.needs_attention
    assert waiting.last_error == "callback_missing"
    completed = complete_lead_callback(db, atlas.id, run.id, lead.id)
    assert completed["status"] == "completed"


def test_webhook_auth_replay_and_cross_organization(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    outsider = make_user(db, "out@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    lead = create_lead(db, atlas.id, admin.id, {"title": "Harbor", "status": "new"})
    key, secret = create_webhook_key(db, atlas.id)
    body = json.dumps(
        {"lead_id": str(lead.id), "body": "Checking in.", "organization_id": str(northwind.id)}
    ).encode()
    forbidden = client.post(
        "/api/v1/hooks/follow-ups/request",
        content=body,
        headers=_signed(key.id, secret, body, "follow-1"),
    )
    assert forbidden.status_code == 403
    assert db.scalar(select(func.count()).select_from(Approval)) == 0

    owned = json.dumps({"lead_id": str(lead.id), "body": "Checking in."}).encode()
    missing = client.post("/api/v1/hooks/follow-ups/request", content=owned)
    assert missing.status_code == 401
    bad = _signed(key.id, "wrong-secret", owned, "follow-2")
    rejected = client.post("/api/v1/hooks/follow-ups/request", content=owned, headers=bad)
    assert rejected.status_code == 401
    stale = _signed(key.id, secret, owned, "follow-3", timestamp=str(int(time.time()) - 3600))
    expired = client.post("/api/v1/hooks/follow-ups/request", content=owned, headers=stale)
    assert expired.status_code == 401

    headers = _signed(key.id, secret, owned, "follow-4")
    first = client.post("/api/v1/hooks/follow-ups/request", content=owned, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/hooks/follow-ups/request", content=owned, headers=headers)
    assert second.json() == first.json()
    changed = json.dumps({"lead_id": str(lead.id), "body": "A different message."}).encode()
    conflict = client.post(
        "/api/v1/hooks/follow-ups/request",
        content=changed,
        headers=_signed(key.id, secret, changed, "follow-4"),
    )
    assert conflict.status_code == 409
    wrong_route = client.post("/api/v1/hooks/follow-ups", content=owned, headers=headers)
    assert wrong_route.status_code == 409
    assert db.scalar(select(func.count()).select_from(Approval)) == 1
    approval = db.scalar(select(Approval))
    assert approval is not None
    assert approval.organization_id == atlas.id
    assert approval.status == ApprovalStatus.pending
    assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0


def test_webhook_rotation_revokes_old_secret_and_reports_fresh_acceptance(
    client: TestClient, db: Session
) -> None:
    admin = make_user(db, "hook-admin@example.com")
    organization = make_organization(db, "Hook rotation", "hook-rotation")
    make_membership(db, admin, organization, MembershipRole.admin)
    csrf = _csrf(login(client, admin.email, PASSWORD))
    path = f"/api/v1/organizations/{organization.id}/integrations/webhook-keys"
    assert client.get(path).json() is None
    response = client.post(path, headers=csrf)
    assert response.status_code == 201
    assert response.headers["Cache-Control"] == "no-store"
    created = response.json()
    key_id = uuid.UUID(created["id"])
    body = b"{}"
    old_headers = _signed(key_id, created["secret"], body, "rotation-before")
    callback = "/api/v1/hooks/follow-ups"
    assert client.post(callback, content=body, headers=old_headers).status_code == 200
    assert client.get(path).json()["last_accepted_at"]
    rotated = client.post(f"{path}/rotate", headers=csrf)
    assert rotated.status_code == 200, rotated.text
    assert rotated.headers["Cache-Control"] == "no-store"
    assert rotated.json()["id"] == created["id"]
    status = client.get(path).json()
    assert "secret" not in status
    assert status["rotated_at"]
    assert status["last_accepted_at"] is None
    assert client.post(callback, content=body, headers=old_headers).status_code == 401
    new_headers = _signed(key_id, rotated.json()["secret"], body, "rotation-after")
    assert client.post(callback, content=body, headers=new_headers).status_code == 200
    assert client.get(path).json()["last_accepted_at"]
    assert client.post(f"{path}/revoke", headers=csrf).status_code == 204
    assert client.get(path).json()["revoked_at"]
    assert client.post(callback, content=body, headers=new_headers).status_code == 401
    reconnected = client.post(f"{path}/rotate", headers=csrf)
    assert reconnected.status_code == 200
    assert client.get(path).json()["revoked_at"] is None
    assert client.get(path).json()["last_accepted_at"] is None
    assert client.post(callback, content=body, headers=new_headers).status_code == 401


def test_webhook_rate_limit_and_payload_cap(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    key, secret = create_webhook_key(db, atlas.id)
    monkeypatch.setenv("ATLAS_WEBHOOK_RATE_LIMIT", "2")
    monkeypatch.setenv("ATLAS_WEBHOOK_MAX_BYTES", "64")
    get_settings.cache_clear()
    try:
        huge = b"{}" + b" " * 80
        limited = client.post(
            "/api/v1/hooks/follow-ups",
            content=huge,
            headers=_signed(key.id, secret, huge, "rate-0"),
        )
        assert limited.status_code == 413
        body = b"{}"
        for index in range(2):
            response = client.post(
                "/api/v1/hooks/follow-ups",
                content=body,
                headers=_signed(key.id, secret, body, f"rate-{index + 1}"),
            )
            assert response.status_code == 200, response.text
        blocked = client.post(
            "/api/v1/hooks/follow-ups",
            content=body,
            headers=_signed(key.id, secret, body, "rate-3"),
        )
        assert blocked.status_code == 429
    finally:
        get_settings.cache_clear()


def test_n8n_stand_in_retries_then_records_the_callback(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP stand-in for n8n. It is not the n8n process."""

    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    create_webhook_key(db, atlas.id)
    failures = {"left": 1}
    received: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            received.append(payload)
            status = 500 if failures["left"] else 200
            failures["left"] = max(0, failures["left"] - 1)
            self.send_response(status)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "ATLAS_N8N_LEAD_WEBHOOK_URL", f"http://127.0.0.1:{server.server_port}/webhook/atlas-lead"
    )
    get_settings.cache_clear()
    ada = login(client, "ada@example.com", PASSWORD)
    try:
        created = client.post(
            f"/api/v1/organizations/{atlas.id}/leads",
            json={"title": "Harbor"},
            headers={"X-CSRF-Token": str(ada["csrf_token"])},
        )
        assert created.status_code == 201, created.text
        db.expire_all()
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.organization_id == atlas.id))
        assert run is not None
        assert run.status == WorkflowStatus.accepted
        assert len(received) == 2
        envelope = received[-1]
        assert isinstance(envelope.get("body_text"), str)
        assert isinstance(envelope.get("headers"), dict)
        headers = {str(name): str(value) for name, value in envelope["headers"].items()}
        callback = client.post(
            "/api/v1/hooks/lead-processed",
            content=str(envelope["body_text"]).encode(),
            headers=headers,
        )
        assert callback.status_code == 200, callback.text
        db.expire_all()
        finished = db.get(WorkflowRun, run.id)
        assert finished is not None
        assert finished.status == WorkflowStatus.completed
    finally:
        server.shutdown()
        get_settings.cache_clear()


def test_n8n_timeout_is_not_retried(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            time.sleep(1)
            self.send_response(200)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    calls = {"count": 0}
    original = Handler.do_POST

    def counting(self: BaseHTTPRequestHandler) -> None:
        calls["count"] += 1
        original(self)

    Handler.do_POST = counting  # type: ignore[method-assign]
    monkeypatch.setenv(
        "ATLAS_N8N_LEAD_WEBHOOK_URL", f"http://127.0.0.1:{server.server_port}/webhook"
    )
    monkeypatch.setenv("ATLAS_N8N_TIMEOUT_SECONDS", "0.2")
    get_settings.cache_clear()
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    create_webhook_key(db, atlas.id)
    try:
        create_lead(db, atlas.id, admin.id, {"title": "Harbor", "status": "new"})
        from app.domains.automation.workflows import dispatch_pending, stage_lead_created

        lead_id = db.scalar(select(WorkflowRun.lead_id))
        assert lead_id is None
        from app.domains.crm.models import Lead

        lead = db.scalar(select(Lead))
        assert lead is not None
        stage_lead_created(db, atlas.id, lead.id, None)
        db.commit()
        dispatch_pending(db, atlas.id)
        db.expire_all()
        run = db.scalar(select(WorkflowRun))
        assert run is not None
        assert run.status == WorkflowStatus.needs_attention
        assert calls["count"] == 1
    finally:
        server.shutdown()
        get_settings.cache_clear()


def test_automation_snapshot_reports_sandbox_and_simulation(
    client: TestClient, db: Session
) -> None:
    admin = make_user(db, "ada@example.com")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    make_membership(db, admin, atlas, MembershipRole.admin)
    anonymous = client.get(f"/api/v1/organizations/{atlas.id}/automations")
    assert anonymous.status_code == 401
    login(client, "ada@example.com", PASSWORD)
    response = client.get(f"/api/v1/organizations/{atlas.id}/automations")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email_mode"] == "sandbox"
    assert body["calendar_provider"] == "simulation"
    assert body["n8n_configured"] is False
    assert {item["trigger"] for item in body["automations"]} == {"lead_created", "schedule"}
    lead = next(item for item in body["automations"] if item["trigger"] == "lead_created")
    assert lead["kind"] == "lead_processing"
    assert lead["completed"] == 0
    assert lead["configured"] is False
    follow_up = next(item for item in body["automations"] if item["kind"] == "follow_up")
    assert follow_up["awaiting_review"] == 0
    assert follow_up["configured"] is False


def test_live_email_requires_an_explicit_switch() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="test",
            secret_key="test-secret-key-must-be-32-chars-min",
            database_url="postgresql+psycopg://atlas:atlas@localhost:5432/atlas",
            email_mode="live",
            email_live_enabled=False,
        )


def _signed(
    key_id: uuid.UUID,
    secret: str,
    body: bytes,
    idempotency_key: str,
    timestamp: str | None = None,
) -> dict[str, str]:
    stamp = timestamp or str(int(time.time()))
    return {
        "Content-Type": "application/json",
        "X-ATLAS-Key-Id": str(key_id),
        "X-ATLAS-Timestamp": stamp,
        "X-ATLAS-Idempotency-Key": idempotency_key,
        "X-ATLAS-Signature": sign_webhook(secret, stamp, idempotency_key, body),
    }


def _email_approval(
    db: Session, email: str = "ada@example.com", slug: str = "atlas-demo"
) -> Approval:
    admin = make_user(db, email)
    atlas = make_organization(db, "Atlas Demo", slug)
    make_membership(db, admin, atlas, MembershipRole.admin)
    company = create_company(db, atlas.id, {"name": "Harbor Logistics"})
    contact = create_contact(
        db,
        atlas.id,
        {
            "full_name": "Ada Contact",
            "email": email,
            "company_id": company.id,
        },
    )
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
        action_type=ActionType.prepare_customer_response,
        payload={
            "body": "We can discuss bonded storage.",
            "to": email,
            "contact_id": str(contact.id),
            "recipient_snapshot": email,
            "subject": "Bonded storage",
        },
        position=0,
    )


def _appointment_approval(
    db: Session,
    shared: tuple[User, Organization] | None = None,
    payload: dict[str, object] | None = None,
) -> tuple[Approval, tuple[User, Organization]]:
    if shared is None:
        admin = make_user(db, "ada@example.com")
        atlas = make_organization(db, "Atlas Demo", "atlas-demo")
        make_membership(db, admin, atlas, MembershipRole.admin)
    else:
        admin, atlas = shared
    inquiry = create_inquiry(
        db, atlas.id, {"subject": f"Visit {uuid.uuid4().hex[:8]}", "body": "Book a visit"}
    )
    run = AgentRun(
        organization_id=atlas.id,
        inquiry_id=inquiry.id,
        started_by=admin.id,
        status=RunStatus.awaiting_approval,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    if payload is None:
        start = datetime.now(UTC) + timedelta(days=3)
        slot = {
            "body": "Appointment requested.",
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=30)).isoformat(),
        }
    else:
        slot = {
            "body": "Appointment requested.",
            "starts_at": payload["starts_at"],
            "ends_at": payload["ends_at"],
        }
    approval = create_approval(
        db,
        organization_id=atlas.id,
        run_id=run.id,
        requested_by=admin.id,
        action_type=ActionType.request_appointment,
        payload=slot,
        position=0,
    )
    return approval, (admin, atlas)


def _lead(db: Session, approval: Approval) -> object:
    from app.domains.crm.models import Lead

    lead = create_lead(
        db,
        approval.organization_id,
        approval.requested_by,
        {
            "title": "Harbor",
            "status": "new",
            "contact_id": approval.payload.get("contact_id"),
        },
    )
    approval.payload = {**approval.payload, "lead_id": str(lead.id)}
    approval.payload_hash = __import__(
        "app.domains.approvals.service", fromlist=["payload_hash"]
    ).payload_hash(approval.payload)
    db.commit()
    stored = db.get(Lead, lead.id)
    assert stored is not None
    return stored


def _messages() -> int:
    assert SINK is not None
    with SINK.lock:
        return len(SINK.messages)
