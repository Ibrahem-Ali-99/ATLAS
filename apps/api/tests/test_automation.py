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
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.automation.signatures import sign_webhook
from app.domains.crm.service import create_inquiry, create_lead
from app.domains.identity.models import MembershipRole, Organization, User
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.smtp_sink import SINK, SmtpSink


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
    cancelled = client.post(
        f"/api/v1/organizations/{approval.organization_id}/calendar/bookings/{booking.id}/cancel",
        headers={"X-CSRF-Token": str(ada["csrf_token"])},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["provider"] == "simulation"


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
    assert db.scalar(select(func.count()).select_from(Approval)) == 1
    approval = db.scalar(select(Approval))
    assert approval is not None
    assert approval.organization_id == atlas.id
    assert approval.status == ApprovalStatus.pending
    assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0


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
            "to": "inbox@localhost",
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
        {"title": "Harbor", "status": "new"},
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
