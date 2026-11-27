# ruff: noqa: E501
"""Run Harbor provider operations and store the provider's own result.

Nothing here marks a provider connected, a message delivered, or a subscription
active unless that provider accepted the call. Customer rows from the source
workspace are not read.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentEvent, AgentRun, RunStatus
from app.domains.approvals.models import ActionType
from app.domains.approvals.service import create_approval, decide, execute_approved
from app.domains.assistant.service import complete_turn, create_conversation, prepare_turn
from app.domains.automation.intents import dispatch_intent
from app.domains.automation.models import (
    BookingStatus,
    CalendarBooking,
    EmailMessage,
    EmailStatus,
    WebhookKey,
    WorkflowKind,
    WorkflowRun,
    WorkflowStatus,
)
from app.domains.automation.workflows import dispatch_workflow
from app.domains.billing.provider import (
    create_checkout_url,
    create_portal_url,
    ensure_customer,
    price_map,
)
from app.domains.billing.service import (
    ensure_plans,
    entitlement_plan_code,
    get_subscription,
    plan_for,
)
from app.domains.crm.models import Company, Contact, Inquiry, Lead, LeadStatus
from app.domains.demo.harbor_providers import GrantResult, restore_grants
from app.domains.identity.models import Membership, MembershipRole, User
from app.domains.inbox.models import InboxConversation, InboxMessage, InboxStatus, WidgetConfig
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.resend_test import deliver_test
from app.domains.integrations.service import open_credentials
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.retrieval import search_chunks
from app.domains.knowledge.vectors import store_chunk_embedding
from app.domains.observability.models import OperationTrace
from app.domains.provenance.origin import Origin
from app.integrations.calendar import WorkspaceCalendar
from app.integrations.google_calendar import active_connection, available
from app.integrations.language import (
    OpenAICompatibleEmbeddingClient,
    get_chat_client,
    get_embedding_client,
)
from app.integrations.smtp_verification import verify_smtp

_CHECK_SOURCE = "harbor-provider-check"
_LOCAL_ORIGINS = ("http://127.0.0.1:3000", "http://localhost:3000")
_N8N_KEY = hashlib.sha256(b"harbor-showcase-lead-processing").hexdigest()
_N8N_RECOVERY_KEY = hashlib.sha256(b"harbor-showcase-lead-processing-callback").hexdigest()
_N8N_LISTENER_KEY = hashlib.sha256(b"harbor-showcase-lead-processing-listener").hexdigest()
_CALLBACK_PORT = 8013


@dataclass(frozen=True)
class StepResult:
    name: str
    status: str
    code: str | None = None
    detail: str = ""


def run(source: Session, harbor: Session) -> list[StepResult]:
    settings = get_settings()
    _refuse_unsafe(settings)
    grants = restore_grants(source, harbor)
    showcase = _showcase(harbor)
    user = _admin(harbor, showcase.id)
    lead, inquiry = _operational_case(harbor, showcase.id, user.id)
    run_row = _open_run(harbor, showcase.id, user.id, inquiry.id)
    steps = [
        _note(harbor, showcase.id, run_row, _grant_step(item), provider=item.kind) for item in grants
    ]
    steps.append(_groq(harbor, showcase.id, run_row))
    steps.append(_embedding_failure(harbor, showcase.id, run_row))
    steps.append(_reembed(harbor, showcase.id, run_row))
    steps.append(_assistant(harbor, showcase.id, user.id, run_row))
    steps.append(_website(harbor, showcase.id, lead, inquiry, run_row))
    steps.append(_whatsapp(harbor, showcase.id, run_row))
    steps.append(_calendar(harbor, showcase.id, user.id, lead, inquiry, run_row))
    steps.append(_follow_up(harbor, showcase.id, user.id, lead, run_row))
    steps.append(_resend(harbor, showcase.id, user.id, run_row))
    steps.append(_smtp(harbor, showcase.id, run_row))
    steps.extend(_n8n(harbor, showcase.id, lead.id, run_row))
    steps.extend(_stripe(harbor, showcase.id, run_row))
    failed = next(
        (item for item in steps if item.status == "failed" and item.name != "embedding_unreachable"),
        None,
    )
    run_row.status = RunStatus.failed if failed is not None else RunStatus.completed
    run_row.finished_at = datetime.now(UTC)
    run_row.error_code = None if failed is None else failed.code
    run_row.error_message = None if failed is None else failed.detail[:500]
    harbor.commit()
    return steps


def _refuse_unsafe(settings: Settings) -> None:
    if settings.environment == "production" or settings.public_demo:
        raise AppError(409, "harbor_runtime_refused", "Harbor provider checks do not run in production")
    if settings.whatsapp_live_enabled or settings.email_live_enabled or settings.campaign_live_enabled:
        raise AppError(
            409,
            "harbor_live_send_refused",
            "Turn off live WhatsApp, live email, and live campaigns before this check",
        )
    if settings.stripe_secret_key.strip() and not settings.stripe_secret_key.startswith(
        ("sk_test_", "rk_test_")
    ):
        raise AppError(409, "harbor_live_charge_refused", "Harbor billing accepts a Stripe test key only")


def _showcase(db: Session):
    from app.domains.demo.harbor_providers import showcase_organization

    return showcase_organization(db)


def _admin(db: Session, organization_id: uuid.UUID) -> User:
    user = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.admin,
        )
    )
    if user is None:
        raise AppError(404, "harbor_admin_missing", "The Harbor showcase has no administrator")
    return user


def _operational_case(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> tuple[Lead, Inquiry]:
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.source == _CHECK_SOURCE,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        company = Company(
            organization_id=organization_id,
            name="Harbor provider check",
            origin=Origin.operational,
        )
        db.add(company)
        db.flush()
        contact = Contact(
            organization_id=organization_id,
            company_id=company.id,
            full_name="Harbor provider check",
            email="harbor-provider-check@harbor.example",
            origin=Origin.operational,
        )
        db.add(contact)
        db.flush()
        lead = Lead(
            organization_id=organization_id,
            company_id=company.id,
            contact_id=contact.id,
            owner_user_id=user_id,
            title="Harbor provider check",
            status=LeadStatus.new,
            source=_CHECK_SOURCE,
            origin=Origin.operational,
        )
        db.add(lead)
        db.flush()
        inquiry = Inquiry(
            organization_id=organization_id,
            company_id=company.id,
            lead_id=lead.id,
            subject="Harbor provider check",
            body="Fictional Harbor request used to exercise provider operations.",
            origin=Origin.operational,
        )
        db.add(inquiry)
        db.commit()
        return lead, inquiry
    inquiry = db.scalar(
        select(Inquiry).where(
            Inquiry.organization_id == organization_id,
            Inquiry.lead_id == lead.id,
            Inquiry.archived_at.is_(None),
        )
    )
    if inquiry is None:
        raise AppError(409, "harbor_inquiry_missing", "The Harbor provider lead has no inquiry")
    return lead, inquiry


def _open_run(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, inquiry_id: uuid.UUID) -> AgentRun:
    row = AgentRun(
        organization_id=organization_id,
        inquiry_id=inquiry_id,
        started_by=user_id,
        status=RunStatus.running,
        origin=Origin.operational,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _note(
    db: Session,
    organization_id: uuid.UUID,
    run_row: AgentRun,
    step: StepResult,
    *,
    provider: str | None = None,
    latency_ms: int | None = None,
) -> StepResult:
    db.add(
        OperationTrace(
            organization_id=organization_id,
            inquiry_id=run_row.inquiry_id,
            agent_run_id=run_row.id,
            operation=step.name[:80],
            status=step.status[:20],
            finished_at=datetime.now(UTC),
            latency_ms=latency_ms,
            provider=None if provider is None else provider[:80],
            error_code=None if step.code is None else step.code[:80],
            langfuse_status="unconfigured",
            detail={"code": step.code, "detail": step.detail[:120]},
        )
    )
    db.add(
        AgentEvent(
            organization_id=organization_id,
            run_id=run_row.id,
            step=step.name[:80],
            status=step.status[:40],
            detail={"code": step.code},
            error_message=None
            if step.status in {"succeeded", "copied", "already_present", "absent"}
            else step.detail[:500],
        )
    )
    db.commit()
    return step


def _grant_step(item: GrantResult) -> StepResult:
    detail = {
        "copied": "Sealed grant copied. Verification is still required.",
        "already_present": "Harbor already has this grant. It was not replaced.",
        "absent": "The operational workspace has no configured grant to copy.",
        "blocked": "The stored grant could not be opened.",
    }[item.status]
    return StepResult(item.kind, item.status, item.code, detail)


def _groq(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    settings = get_settings()
    if settings.llm_provider != "groq" or not settings.llm_api_key.strip():
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("groq", "blocked", "llm_unconfigured", "Groq is not the configured chat provider"),
            provider="groq",
        )
    started = time.perf_counter()
    try:
        answer = get_chat_client(db, organization_id, for_verification=True).complete(
            "Respond with one short word.",
            "verification",
        )
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("groq", "failed", exc.code, exc.message),
            provider="groq",
            latency_ms=_ms(started),
        )
    if not answer.strip():
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("groq", "failed", "llm_failed", "Groq returned an empty answer"),
            provider="groq",
            latency_ms=_ms(started),
        )
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("groq", "succeeded", None, "Groq accepted a connection test"),
        provider="groq",
        latency_ms=_ms(started),
    )


def _embedding_failure(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    settings = get_settings().model_copy(update={"embedding_base_url": "http://127.0.0.1:9/v1"})
    started = time.perf_counter()
    try:
        OpenAICompatibleEmbeddingClient(settings).embed(["harbor"])
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("embedding_unreachable", "failed", exc.code, exc.message),
            provider="ollama",
            latency_ms=_ms(started),
        )
    return _note(
        db,
        organization_id,
        run_row,
        StepResult(
            "embedding_unreachable",
            "failed",
            "embedding_unexpected",
            "A closed port returned an embedding",
        ),
        provider="ollama",
        latency_ms=_ms(started),
    )


def _reembed(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    settings = get_settings()
    if settings.embedding_provider != "ollama":
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("ollama", "blocked", "embedding_unconfigured", "Ollama is not the embedding provider"),
            provider="ollama",
        )
    chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.organization_id == organization_id,
                Chunk.document_id.in_(
                    select(Document.id).where(
                        Document.organization_id == organization_id,
                        Document.status == DocumentStatus.ready,
                    )
                ),
            )
        )
    )
    started = time.perf_counter()
    try:
        vectors = get_embedding_client(db, organization_id, for_verification=True).embed(
            [chunk.content for chunk in chunks]
        )
    except AppError as exc:
        _mark_embedding(db, organization_id, verified=False, detail=exc.message)
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("ollama", "failed", exc.code, exc.message),
            provider="ollama",
            latency_ms=_ms(started),
        )
    if len(vectors) != len(chunks):
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("ollama", "failed", "embedding_failed", "Ollama returned the wrong number of vectors"),
            provider="ollama",
            latency_ms=_ms(started),
        )
    try:
        for chunk, vector in zip(chunks, vectors, strict=True):
            store_chunk_embedding(chunk, vector, settings)
    except AppError as exc:
        db.rollback()
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("ollama", "failed", exc.code, exc.message),
            provider="ollama",
            latency_ms=_ms(started),
        )
    try:
        hits = search_chunks(
            db,
            organization_id,
            "north pier bonded warehousing",
            get_embedding_client(db, organization_id),
            limit=3,
        )
    except AppError as exc:
        db.rollback()
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("ollama", "failed", exc.code, exc.message),
            provider="ollama",
            latency_ms=_ms(started),
        )
    _mark_embedding(db, organization_id, verified=True, detail="Ollama indexed the Harbor library")
    db.commit()
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("ollama", "succeeded", None, f"Ollama embedded {len(chunks)} passages and search returned {len(hits)}"),
        provider="ollama",
        latency_ms=_ms(started),
    )


def _assistant(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    started = time.perf_counter()
    conversation = create_conversation(db, organization_id, user_id, "Harbor provider check")
    try:
        turn = prepare_turn(
            db,
            organization_id,
            user_id,
            conversation.id,
            "What does the bonded warehousing note say about the north pier?",
            get_embedding_client(db, organization_id),
            get_chat_client(db, organization_id),
        )
        if not turn.needs_model:
            return _note(
                db,
                organization_id,
                run_row,
                StepResult(
                    "assistant",
                    "blocked",
                    "assistant_did_not_call_model",
                    "The assistant answered without calling Groq",
                ),
                provider="groq",
                latency_ms=_ms(started),
            )
        reply = complete_turn(db, turn, get_chat_client(db, organization_id))
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("assistant", "failed", exc.code, exc.message),
            provider="groq",
            latency_ms=_ms(started),
        )
    if not reply.message.content.strip():
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("assistant", "failed", "llm_failed", "Groq returned an empty assistant answer"),
            provider="groq",
            latency_ms=_ms(started),
        )
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("assistant", "succeeded", None, f"Groq answered with document search {reply.document_search}"),
        provider="groq",
        latency_ms=_ms(started),
    )


def _resend_feedback(confirmation: str, event: str) -> StepResult:
    delivered = event in {"delivered", "opened", "clicked"}
    failed = event in {"bounced", "complained", "failed"}
    if delivered:
        detail = (
            f"Resend {confirmation} the test. A later read reported last_event {event}, "
            "which is delivery feedback and not the same as acceptance"
        )
        return StepResult("resend", "succeeded", None, detail)
    if failed:
        return StepResult(
            "resend",
            "failed",
            f"resend_{event}",
            f"Resend {confirmation} the test, then reported last_event {event}",
        )
    if event == "unavailable":
        return StepResult(
            "resend",
            "succeeded",
            None,
            f"Resend {confirmation} the test. This key cannot read delivery events, so acceptance was not treated as delivery",
        )
    return StepResult(
        "resend",
        "succeeded",
        None,
        f"Resend {confirmation} the test. The latest provider event is {event}, which is not delivery confirmation",
    )


def _next_n8n_key(db: Session) -> str | None:
    order = (_N8N_KEY, _N8N_RECOVERY_KEY, _N8N_LISTENER_KEY)
    runs = {
        key: db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key)) for key in order
    }
    for key in order:
        run = runs[key]
        if run is None:
            return key
        if run.status == WorkflowStatus.completed:
            return None
    return None


def _latest_n8n_run(db: Session) -> WorkflowRun:
    order = (_N8N_LISTENER_KEY, _N8N_RECOVERY_KEY, _N8N_KEY)
    for key in order:
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key))
        if run is not None:
            return run
    raise AppError(409, "n8n_not_configured", "Harbor has no n8n run to report")


def _listener_is_local() -> bool:
    for _attempt in range(10):
        try:
            response = httpx.get(f"http://127.0.0.1:{_CALLBACK_PORT}/health", timeout=1)
        except httpx.HTTPError:
            time.sleep(0.1)
            continue
        if response.status_code == 200 and response.text == "harbor-listener":
            return True
        return False
    return False


def _n8n_note(
    db: Session,
    organization_id: uuid.UUID,
    run_row: AgentRun,
    workflow: WorkflowRun,
    *,
    recovered: bool,
) -> StepResult:
    completed = workflow.status == WorkflowStatus.completed
    label = "Recovery n8n run" if recovered else "Stored n8n run"
    if completed:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("n8n", "succeeded", None, f"{label} completed after a signed callback"),
            provider="n8n",
        )
    failed = workflow.status in {WorkflowStatus.failed, WorkflowStatus.needs_attention}
    return _note(
        db,
        organization_id,
        run_row,
        StepResult(
            "n8n",
            "failed" if failed else "blocked",
            workflow.last_error or workflow.status.value,
            f"{label} status is {workflow.status.value}",
        ),
        provider="n8n",
    )


def _stripe_observed(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> list[StepResult]:
    row = get_subscription(db, organization_id)
    plan = entitlement_plan_code(row)
    if plan == "free" and not row.provider_subscription_id:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult(
                    "stripe_entitlement",
                    "blocked",
                    "webhook_not_delivered",
                    "The plan stays Free until Stripe posts a signed webhook to the Harbor API. No subscription was marked active",
                ),
                provider="stripe",
            )
        ]
    return [
        _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "stripe_entitlement",
                "succeeded",
                None,
                f"Stripe reports the {plan} plan on the signed subscription",
            ),
            provider="stripe",
        )
    ]


def _monitoring(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    from app.domains.monitoring.service import diagnostics, trace_run

    traced = trace_run(db, organization_id, run_row.id)
    report = diagnostics(db, organization_id)
    if not traced["events"] or not traced["traces"] or traced["run"]["id"] != run_row.id:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("monitoring", "failed", "monitoring_empty", "Monitoring could not read this agent run"),
            provider="atlas",
        )
    earlier = len(report["integration_failures"])
    return _note(
        db,
        organization_id,
        run_row,
        StepResult(
            "monitoring",
            "succeeded",
            None,
            f"Monitoring can read this agent run. {earlier} earlier workflow failures remain visible",
        ),
        provider="atlas",
    )


def record_billing(harbor: Session) -> list[StepResult]:
    """Record the subscription Stripe currently reports. Does not mark a plan active itself."""

    _refuse_unsafe(get_settings())
    showcase = _showcase(harbor)
    user = _admin(harbor, showcase.id)
    _lead, inquiry = _operational_case(harbor, showcase.id, user.id)
    run_row = _open_run(harbor, showcase.id, user.id, inquiry.id)
    steps = _stripe_observed(harbor, showcase.id, run_row)
    row = get_subscription(harbor, showcase.id)
    plan = entitlement_plan_code(row)
    if plan != "free" and row.provider_customer_id:
        try:
            portal = create_portal_url(row.provider_customer_id)
        except AppError as exc:
            steps.append(
                _note(
                    harbor,
                    showcase.id,
                    run_row,
                    StepResult("stripe_portal", "failed", exc.code, exc.message),
                    provider="stripe",
                )
            )
        else:
            opened = portal.startswith("https://billing.stripe.com/")
            steps.append(
                _note(
                    harbor,
                    showcase.id,
                    run_row,
                    StepResult(
                        "stripe_portal",
                        "succeeded" if opened else "failed",
                        None if opened else "billing_portal_unavailable",
                        "Stripe opened a customer portal session"
                        if opened
                        else "Stripe did not return a customer portal session",
                    ),
                    provider="stripe",
                )
            )
    _finish_run(run_row, steps)
    harbor.commit()
    return steps


def accept_whatsapp(harbor: Session) -> list[StepResult]:
    """Confirm the stored WhatsApp token with Graph and record that result.

    This reads the phone number. It does not send a message or change a webhook.
    """

    settings = get_settings()
    _refuse_unsafe(settings)
    showcase = _showcase(harbor)
    user = _admin(harbor, showcase.id)
    _lead, inquiry = _operational_case(harbor, showcase.id, user.id)
    run_row = _open_run(harbor, showcase.id, user.id, inquiry.id)
    steps = [_whatsapp(harbor, showcase.id, run_row)]
    _finish_run(run_row, steps)
    harbor.commit()
    return steps


def refresh_resend(harbor: Session) -> list[StepResult]:
    """Read delivery feedback for the stored Resend test. Does not send again."""

    from app.domains.integrations.resend_test import refresh_delivery, test_status

    _refuse_unsafe(get_settings())
    showcase = _showcase(harbor)
    user = _admin(harbor, showcase.id)
    _lead, inquiry = _operational_case(harbor, showcase.id, user.id)
    run_row = _open_run(harbor, showcase.id, user.id, inquiry.id)
    status = test_status(harbor, showcase.id)
    if not status.credential_configured:
        steps = [
            _note(
                harbor,
                showcase.id,
                run_row,
                StepResult(
                    "resend",
                    "blocked",
                    "resend_test_unconfigured",
                    "Harbor has no Resend sending key. No test was sent",
                ),
                provider="resend",
            )
        ]
    else:
        try:
            event = refresh_delivery(harbor, showcase.id)
        except AppError as exc:
            blocked = exc.code == "resend_test_unconfirmed"
            steps = [
                _note(
                    harbor,
                    showcase.id,
                    run_row,
                    StepResult(
                        "resend",
                        "blocked" if blocked else "failed",
                        exc.code,
                        exc.message if blocked else exc.message,
                    ),
                    provider="resend",
                )
            ]
        else:
            refreshed = test_status(harbor, showcase.id)
            steps = [
                _note(
                    harbor,
                    showcase.id,
                    run_row,
                    _resend_feedback(refreshed.provider_confirmation or "accepted", event),
                    provider="resend",
                )
            ]
    _finish_run(run_row, steps)
    harbor.commit()
    return steps


def continue_journeys(harbor: Session) -> list[StepResult]:
    """Finish Harbor routes that do not copy grants or repeat a completed provider call.

    Public model replies are enabled only inside this process, and only for the
    website step. The operational environment file is not changed.
    """

    _refuse_unsafe(get_settings())
    showcase = _showcase(harbor)
    user = _admin(harbor, showcase.id)
    lead, inquiry = _operational_case(harbor, showcase.id, user.id)
    run_row = _open_run(harbor, showcase.id, user.id, inquiry.id)
    steps = [_website_with_showcase_inference(harbor, showcase.id, lead, inquiry, run_row)]
    steps.append(_resend(harbor, showcase.id, user.id, run_row))
    steps.extend(_n8n(harbor, showcase.id, lead.id, run_row))
    steps.append(_whatsapp(harbor, showcase.id, run_row))
    steps.extend(_stripe_observed(harbor, showcase.id, run_row))
    _finish_run(run_row, steps)
    harbor.commit()
    steps.append(_monitoring(harbor, showcase.id, run_row))
    _finish_run(run_row, steps)
    harbor.commit()
    return steps


def _website_with_showcase_inference(
    db: Session,
    organization_id: uuid.UUID,
    lead: Lead,
    inquiry: Inquiry,
    run_row: AgentRun,
) -> StepResult:
    import os

    previous = os.environ.get("ATLAS_PUBLIC_INFERENCE_ENABLED")
    os.environ["ATLAS_PUBLIC_INFERENCE_ENABLED"] = "true"
    get_settings.cache_clear()
    try:
        return _website(db, organization_id, lead, inquiry, run_row)
    finally:
        if previous is None:
            os.environ.pop("ATLAS_PUBLIC_INFERENCE_ENABLED", None)
        else:
            os.environ["ATLAS_PUBLIC_INFERENCE_ENABLED"] = previous
        get_settings.cache_clear()


def _finish_run(run_row: AgentRun, steps: list[StepResult]) -> None:
    failed = next(
        (item for item in steps if item.status == "failed" and item.name != "embedding_unreachable"),
        None,
    )
    run_row.status = RunStatus.failed if failed is not None else RunStatus.completed
    run_row.finished_at = datetime.now(UTC)
    run_row.error_code = None if failed is None else failed.code
    run_row.error_message = None if failed is None else failed.detail[:500]


def _website(
    db: Session,
    organization_id: uuid.UUID,
    lead: Lead,
    inquiry: Inquiry,
    run_row: AgentRun,
) -> StepResult:
    del inquiry
    question = "What is the north-pier bonded warehousing rule?"
    stored = db.scalar(
        select(InboxMessage)
        .join(InboxConversation, InboxConversation.id == InboxMessage.conversation_id)
        .where(
            InboxMessage.organization_id == organization_id,
            InboxConversation.organization_id == organization_id,
            InboxConversation.lead_id == lead.id,
            InboxConversation.channel == "webchat",
            InboxMessage.direction == "outbound",
            InboxMessage.sender == "ATLAS AI",
        )
    )
    if stored is not None:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "website_chat",
                "succeeded",
                None,
                "A grounded website reply is already stored on the Harbor lead. The model was not called again",
            ),
            provider="webchat",
        )
    widget = _widget(db, organization_id)
    conversation = InboxConversation(
        organization_id=organization_id,
        contact_id=lead.contact_id,
        lead_id=lead.id,
        subject="North pier warehousing",
        channel="webchat",
        status=InboxStatus.open,
    )
    db.add(conversation)
    db.flush()
    db.add(
        InboxMessage(
            organization_id=organization_id,
            conversation_id=conversation.id,
            sender="visitor",
            recipient="ATLAS",
            body=question,
            direction="inbound",
            channel="webchat",
            delivery_status="received",
            provider_message_id=f"harbor-web-{uuid.uuid4()}",
        )
    )
    db.commit()
    if not get_settings().public_inference_enabled:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "website_chat",
                "blocked",
                "public_inference_disabled",
                "The visitor message is in Inbox. Public model replies stay off until ATLAS_PUBLIC_INFERENCE_ENABLED is set",
            ),
            provider="webchat",
        )
    from app.api.v1.inbox import evaluate_inbox_draft
    from app.domains.assistant.inference_guard import (
        assess_public_inference,
        finish_public_inference,
    )
    from app.domains.crm import service as crm

    decision = assess_public_inference(
        f"harbor-website:{organization_id}", question, hold_slot=True
    )
    if not decision.allowed:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("website_chat", "blocked", decision.code, decision.message),
            provider="webchat",
        )
    try:
        try:
            draft = evaluate_inbox_draft(
                db,
                organization_id,
                conversation.id,
                question,
                get_embedding_client(db, organization_id),
                get_chat_client(
                    db,
                    organization_id,
                    max_output_tokens=get_settings().public_inference_max_output_tokens,
                    public_inference=True,
                ),
            )
        except AppError as exc:
            return _note(
                db,
                organization_id,
                run_row,
                StepResult("website_chat", "failed", exc.code, exc.message),
                provider="webchat",
            )
        body = _draft_body(draft)
        if draft.get("grounding") != "grounded" or body is None:
            return _note(
                db,
                organization_id,
                run_row,
                StepResult(
                    "website_chat",
                    "failed",
                    "insufficient_evidence",
                    "Groq answered, and the reply was not stored because retrieval was not grounded",
                ),
                provider="webchat",
            )
        crm.create_inquiry(
            db,
            organization_id,
            {
                "company_id": lead.company_id,
                "lead_id": lead.id,
                "subject": "North pier warehousing",
                "body": question,
                "origin": Origin.operational,
            },
            commit=False,
        )
        db.add(
            InboxMessage(
                organization_id=organization_id,
                conversation_id=conversation.id,
                sender="ATLAS AI",
                recipient="visitor",
                body=body,
                direction="outbound",
                channel="webchat",
                delivery_status="sent",
                provider_message_id=f"harbor-web-reply-{uuid.uuid4()}",
            )
        )
        widget.operating_mode = "ai_auto_reply"
        db.commit()
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "website_chat",
                "succeeded",
                None,
                "Groq stored a grounded website reply on the Harbor provider-check lead. Public reply budgets still apply",
            ),
            provider="webchat",
        )
    finally:
        finish_public_inference()


def _whatsapp(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    record = _integration(db, organization_id, IntegrationType.whatsapp)
    if record is None or not record.encrypted_credentials:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("whatsapp", "blocked", "whatsapp_unconfigured", "Harbor has no WhatsApp credential"),
            provider="meta",
        )
    if get_settings().whatsapp_live_enabled:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("whatsapp", "blocked", "whatsapp_live_refused", "Live WhatsApp stays off for this check"),
            provider="meta",
        )
    started = time.perf_counter()
    try:
        _confirm_whatsapp(record)
    except AppError as exc:
        record.verified_at = None
        record.verification_detail = exc.message[:500]
        record.status = IntegrationStatus.verification_failed
        db.commit()
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("whatsapp", "failed", exc.code, exc.message),
            provider="meta",
            latency_ms=_ms(started),
        )
    record.verified_at = datetime.now(UTC)
    record.verification_detail = "Meta confirmed the configured phone number"
    record.status = IntegrationStatus.configured
    db.commit()
    accepted = _note(
        db,
        organization_id,
        run_row,
        StepResult(
            "whatsapp",
            "succeeded",
            None,
            "Meta confirmed the configured phone number. No message was sent",
        ),
        provider="meta",
        latency_ms=_ms(started),
    )
    inbound = db.scalar(
        select(InboxMessage.id).where(
            InboxMessage.organization_id == organization_id,
            InboxMessage.channel == "whatsapp",
            InboxMessage.direction == "inbound",
            InboxMessage.provider_message_id.notlike("harbor-%"),
        )
    )
    if inbound is None:
        _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "whatsapp_inbound",
                "blocked",
                "whatsapp_inbound_required",
                "Meta accepted the connection. Inbound stays on the operational webhook. No reply was sent",
            ),
            provider="meta",
        )
        return accepted
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("whatsapp_inbound", "succeeded", None, "Meta confirmed the number and Harbor has an inbound message"),
        provider="meta",
        latency_ms=_ms(started),
    )


def _calendar(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    lead: Lead,
    inquiry: Inquiry,
    run_row: AgentRun,
) -> StepResult:
    connection = active_connection(db, organization_id)
    if connection is None:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "google_calendar",
                "blocked",
                "calendar_disconnected",
                "Reconnect Google Calendar from the Harbor administrator session",
            ),
            provider="google",
        )
    stuck = db.scalar(
        select(CalendarBooking).where(
            CalendarBooking.organization_id == organization_id,
            CalendarBooking.lead_id == lead.id,
            CalendarBooking.provider == "google",
            CalendarBooking.status == BookingStatus.booked,
        )
    )
    if stuck is not None:
        try:
            WorkspaceCalendar().cancel(db, organization_id, stuck.id)
        except AppError as exc:
            return _note(
                db,
                organization_id,
                run_row,
                StepResult("google_calendar", "failed", exc.code, exc.message),
                provider="google",
            )
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "succeeded", None, "Google cancellation recovered an open Harbor booking"),
            provider="google",
        )
    cancelled = db.scalar(
        select(CalendarBooking.id).where(
            CalendarBooking.organization_id == organization_id,
            CalendarBooking.lead_id == lead.id,
            CalendarBooking.provider == "google",
            CalendarBooking.status == BookingStatus.cancelled,
            CalendarBooking.provider_event_id.is_not(None),
        )
    )
    if cancelled is not None:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "google_calendar",
                "succeeded",
                None,
                "A stored Google booking for this check is already cancelled",
            ),
            provider="google",
        )
    started = time.perf_counter()
    try:
        slot = _free_slot(db, organization_id, connection)
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "failed", exc.code, exc.message),
            provider="google",
            latency_ms=_ms(started),
        )
    if slot is None:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "failed", "slot_unavailable", "Google reported every checked slot busy"),
            provider="google",
            latency_ms=_ms(started),
        )
    starts_at, ends_at = slot
    booking_run = AgentRun(
        organization_id=organization_id,
        inquiry_id=inquiry.id,
        started_by=user_id,
        status=RunStatus.awaiting_approval,
        origin=Origin.operational,
    )
    db.add(booking_run)
    db.flush()
    approval = create_approval(
        db,
        organization_id=organization_id,
        run_id=booking_run.id,
        requested_by=user_id,
        action_type=ActionType.request_appointment,
        position=0,
        payload={
            "lead_id": str(lead.id),
            "body": "Harbor provider appointment",
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    decide(db, organization_id, approval.id, user_id, approved=True, note="Harbor provider check")
    try:
        result = execute_approved(db, organization_id, approval.id)
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "failed", exc.code, exc.message),
            provider="google",
            latency_ms=_ms(started),
        )
    booking_id = result.get("booking_id")
    if not isinstance(booking_id, str):
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "failed", "calendar_provider_error", "Google booking did not return an id"),
            provider="google",
            latency_ms=_ms(started),
        )
    booking = db.get(CalendarBooking, uuid.UUID(booking_id))
    if booking is None or booking.provider != "google" or not booking.provider_event_id:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "failed", "calendar_provider_error", "The booking is not a Google event"),
            provider="google",
            latency_ms=_ms(started),
        )
    try:
        WorkspaceCalendar().cancel(db, organization_id, booking.id)
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "google_calendar",
                "failed",
                exc.code,
                "Google created the private event and cancellation failed. The booking remains",
            ),
            provider="google",
            latency_ms=_ms(started),
        )
    db.refresh(booking)
    if booking.status != BookingStatus.cancelled:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("google_calendar", "failed", "calendar_provider_error", "The Google booking was not cancelled"),
            provider="google",
            latency_ms=_ms(started),
        )
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("google_calendar", "succeeded", None, "Google accepted a private event and then cancelled it"),
        provider="google",
        latency_ms=_ms(started),
    )


def _follow_up(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    lead: Lead,
    run_row: AgentRun,
) -> StepResult:
    settings = get_settings()
    if settings.email_mode != "sandbox":
        return _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "follow_up",
                "blocked",
                "sandbox_email_required",
                "Approved follow-up stays queued until email mode is the local sandbox",
            ),
            provider="smtp",
        )
    sent = db.scalar(
        select(EmailMessage.id).where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.lead_id == lead.id,
            EmailMessage.mode == "sandbox",
            EmailMessage.status == EmailStatus.sent,
        )
    )
    if sent is not None:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("follow_up", "succeeded", None, "The local mailbox already accepted this follow-up"),
            provider="smtp",
        )
    contact = db.get(Contact, lead.contact_id) if lead.contact_id else None
    if contact is None or not contact.email:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("follow_up", "blocked", "invalid_recipient", "The Harbor check contact has no email"),
            provider="smtp",
        )
    mail_run = AgentRun(
        organization_id=organization_id,
        inquiry_id=run_row.inquiry_id,
        started_by=user_id,
        status=RunStatus.awaiting_approval,
        origin=Origin.operational,
    )
    db.add(mail_run)
    db.flush()
    approval = create_approval(
        db,
        organization_id=organization_id,
        run_id=mail_run.id,
        requested_by=user_id,
        action_type=ActionType.prepare_customer_response,
        position=0,
        payload={
            "lead_id": str(lead.id),
            "contact_id": str(contact.id),
            "channel": "email",
            "to": contact.email,
            "recipient_snapshot": contact.email,
            "subject": "Harbor provider check",
            "body": "This sandbox message confirms approved follow-up delivery.",
        },
    )
    decide(db, organization_id, approval.id, user_id, approved=True, note="Harbor provider check")
    started = time.perf_counter()
    try:
        queued = execute_approved(db, organization_id, approval.id)
        if queued.get("status") == "queued":
            dispatch_intent(db, organization_id, uuid.UUID(str(queued["intent_id"])))
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("follow_up", "failed", exc.code, exc.message),
            provider="smtp",
            latency_ms=_ms(started),
        )
    message = db.scalar(
        select(EmailMessage)
        .where(EmailMessage.organization_id == organization_id, EmailMessage.lead_id == lead.id)
        .order_by(EmailMessage.created_at.desc())
    )
    if message is None or message.status.value != "sent" or message.mode != "sandbox":
        status = None if message is None else message.status.value
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("follow_up", "failed", "delivery_failed", f"Sandbox mailbox status is {status}"),
            provider="smtp",
            latency_ms=_ms(started),
        )
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("follow_up", "succeeded", None, "The local mailbox accepted the approved follow-up"),
        provider="smtp",
        latency_ms=_ms(started),
    )


def _resend(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    from app.domains.integrations.resend_test import test_status

    status = test_status(db, organization_id)
    if not status.credential_configured:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("resend", "blocked", "resend_test_unconfigured", "Harbor has no Resend sending key"),
            provider="resend",
        )
    if status.test_delivery_verified and status.provider_confirmation in {"accepted", "retrieved"}:
        from app.domains.integrations.resend_test import refresh_delivery

        try:
            event = refresh_delivery(db, organization_id)
        except AppError as exc:
            return _note(
                db,
                organization_id,
                run_row,
                StepResult("resend", "failed", exc.code, exc.message),
                provider="resend",
            )
        return _note(
            db,
            organization_id,
            run_row,
            _resend_feedback(status.provider_confirmation or "accepted", event),
            provider="resend",
        )
    started = time.perf_counter()
    try:
        receipt = deliver_test(db, organization_id, user_id, "delivered@resend.dev")
    except AppError as exc:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("resend", "failed", exc.code, exc.message),
            provider="resend",
            latency_ms=_ms(started),
        )
    return _note(
        db,
        organization_id,
        run_row,
        _resend_feedback(
            receipt.provider_confirmation,
            receipt.status.provider_last_event or "not_reported",
        ),
        provider="resend",
        latency_ms=_ms(started),
    )


def _smtp(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> StepResult:
    record = _integration(db, organization_id, IntegrationType.email)
    if record is None:
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("smtp", "absent", None, "Harbor has no email integration row"),
            provider="smtp",
        )
    host = record.config.get("host")
    port = record.config.get("port")
    if not isinstance(host, str) or not isinstance(port, int):
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("smtp", "blocked", "email_unconfigured", "Email host or port is missing"),
            provider="smtp",
        )
    username, password = _smtp_login(record)
    result = verify_smtp(
        host=host,
        port=port,
        username=username,
        password=password,
        starttls=bool(record.config.get("starttls", False)),
        use_tls=bool(record.config.get("use_tls", False)),
    )
    if not result.verified:
        record.verified_at = None
        record.verification_detail = result.detail[:500]
        db.commit()
        return _note(
            db,
            organization_id,
            run_row,
            StepResult("smtp", "failed", "smtp_verification_failed", result.detail),
            provider="smtp",
        )
    record.verified_at = datetime.now(UTC)
    record.verification_detail = result.detail[:500]
    record.status = IntegrationStatus.configured
    db.commit()
    return _note(
        db,
        organization_id,
        run_row,
        StepResult("smtp", "succeeded", None, "SMTP accepted the connection test"),
        provider="smtp",
    )


def _n8n(db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID, run_row: AgentRun) -> list[StepResult]:
    settings = get_settings()
    if not settings.n8n_lead_webhook_url.strip():
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("n8n", "blocked", "n8n_not_configured", "ATLAS_N8N_LEAD_WEBHOOK_URL is empty"),
                provider="n8n",
            )
        ]
    idempotency_key = _next_n8n_key(db)
    if idempotency_key is None:
        stored = _latest_n8n_run(db)
        return [_n8n_note(db, organization_id, run_row, stored, recovered=stored.idempotency_key != _N8N_KEY)]
    key = db.scalar(
        select(WebhookKey).where(
            WebhookKey.organization_id == organization_id,
            WebhookKey.revoked_at.is_(None),
        )
    )
    if key is None:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("n8n", "blocked", "n8n_not_configured", "Harbor has no signing key"),
                provider="n8n",
            )
        ]
    workflow = WorkflowRun(
        organization_id=organization_id,
        kind=WorkflowKind.lead_processing,
        status=WorkflowStatus.pending,
        idempotency_key=idempotency_key,
        lead_id=lead_id,
        agent_run_id=run_row.id,
        payload={"outcome": "provider_check"},
        origin=Origin.operational,
        attempt_count=0,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    try:
        server = ThreadingHTTPServer(("0.0.0.0", _CALLBACK_PORT), _LeadCallback)
    except OSError:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult(
                    "n8n",
                    "blocked",
                    "harbor_callback_unavailable",
                    "Port 8013 is in use, so the Harbor callback listener did not start and n8n was not called",
                ),
                provider="n8n",
            )
        ]
    _LeadCallback.engine = db.get_bind()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if not _listener_is_local():
        server.shutdown()
        thread.join(timeout=2)
        workflow.status = WorkflowStatus.failed
        workflow.last_error = "harbor_callback_unavailable"
        db.commit()
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult(
                    "n8n",
                    "failed",
                    "harbor_callback_unavailable",
                    "Port 8013 did not answer from the Harbor listener, so n8n was not called",
                ),
                provider="n8n",
            )
        ]
    previous = _swap_public_api(f"http://host.docker.internal:{_CALLBACK_PORT}")
    started = time.perf_counter()
    dispatch_error: AppError | None = None
    try:
        dispatch_workflow(db, organization_id, workflow.id)
        deadline = time.time() + 20
        while time.time() < deadline:
            db.refresh(workflow)
            if workflow.status == WorkflowStatus.completed:
                break
            time.sleep(0.5)
    except AppError as exc:
        dispatch_error = exc
    finally:
        _swap_public_api(previous)
        server.shutdown()
        thread.join(timeout=2)
    if dispatch_error is not None:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("n8n", "failed", dispatch_error.code, dispatch_error.message),
                provider="n8n",
                latency_ms=_ms(started),
            )
        ]
    db.refresh(workflow)
    if workflow.status == WorkflowStatus.completed:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("n8n", "succeeded", None, "n8n accepted the lead and the signed callback completed the run"),
                provider="n8n",
                latency_ms=_ms(started),
            )
        ]
    if workflow.status == WorkflowStatus.accepted:
        workflow.status = WorkflowStatus.needs_attention
        workflow.last_error = "callback_missing"
        db.commit()
    return [
        _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "n8n",
                "failed" if workflow.status in {WorkflowStatus.failed, WorkflowStatus.needs_attention} else "blocked",
                workflow.last_error or workflow.status.value,
                f"n8n run status is {workflow.status.value}",
            ),
            provider="n8n",
            latency_ms=_ms(started),
        )
    ]


def _stripe(db: Session, organization_id: uuid.UUID, run_row: AgentRun) -> list[StepResult]:
    settings = get_settings()
    if settings.billing_provider != "stripe":
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("stripe", "blocked", "billing_provider_unavailable", "Billing is not in Stripe test mode"),
                provider="stripe",
            )
        ]
    try:
        selection = next(iter(price_map()))
        plan_code, interval = selection.split(":", 1)
        ensure_plans(db)
        plan_for(db, plan_code)
        row = get_subscription(db, organization_id, lock=True)
        if row.provider_customer_id is None:
            row.provider_customer_id = ensure_customer(str(organization_id))
            db.commit()
        create_checkout_url(plan_code, interval, str(organization_id), row.provider_customer_id)
    except AppError as exc:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("stripe", "failed", exc.code, exc.message),
                provider="stripe",
            )
        ]
    except StopIteration:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult("stripe", "blocked", "billing_price_unavailable", "No Stripe test price is configured"),
                provider="stripe",
            )
        ]
    db.refresh(row)
    plan = entitlement_plan_code(row)
    if plan != "free" or row.provider_subscription_id:
        return [
            _note(
                db,
                organization_id,
                run_row,
                StepResult(
                    "stripe",
                    "failed",
                    "billing_unconfirmed",
                    "Entitlements changed without a signed webhook. That result was not accepted",
                ),
                provider="stripe",
            )
        ]
    return [
        _note(
            db,
            organization_id,
            run_row,
            StepResult("stripe_checkout", "succeeded", None, "Stripe test mode opened a checkout session"),
            provider="stripe",
        ),
        _note(
            db,
            organization_id,
            run_row,
            StepResult(
                "stripe_entitlement",
                "blocked",
                "webhook_not_delivered",
                "The plan stays Free until Stripe posts a signed webhook to the Harbor API. No subscription was marked active",
            ),
            provider="stripe",
        ),
    ]


def _confirm_whatsapp(record: IntegrationConfig) -> None:
    credentials = open_credentials(record) or ""
    try:
        payload = json.loads(credentials)
    except json.JSONDecodeError as exc:
        raise AppError(422, "whatsapp_credentials_invalid", "WhatsApp credentials are invalid") from exc
    token = payload.get("access_token") if isinstance(payload, dict) else None
    phone_id = record.config.get("phone_number_id")
    if not isinstance(token, str) or not token or not isinstance(phone_id, str) or not phone_id:
        raise AppError(
            422,
            "whatsapp_configuration_incomplete",
            "WhatsApp phone number ID and access token are required",
        )
    try:
        response = httpx.get(
            f"https://graph.facebook.com/v21.0/{phone_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except httpx.TimeoutException as exc:
        raise AppError(504, "whatsapp_provider_timeout", "WhatsApp connection test timed out") from exc
    except httpx.HTTPError as exc:
        raise AppError(502, "whatsapp_unreachable", "WhatsApp could not be reached") from exc
    if response.status_code >= 400:
        subcode = None
        try:
            provider_error = response.json().get("error", {})
        except ValueError:
            provider_error = {}
        if isinstance(provider_error, dict):
            subcode = provider_error.get("error_subcode")
        if subcode == 463:
            raise AppError(422, "whatsapp_credentials_expired", "WhatsApp access token expired")
        raise AppError(502, "whatsapp_provider_error", "WhatsApp rejected the connection test")
    try:
        confirmed = response.json().get("id")
    except ValueError as exc:
        raise AppError(502, "whatsapp_provider_error", "WhatsApp could not confirm this phone number") from exc
    if confirmed != phone_id:
        raise AppError(502, "whatsapp_provider_error", "WhatsApp could not confirm this phone number")


def _widget(db: Session, organization_id: uuid.UUID) -> WidgetConfig:
    widget = db.scalar(select(WidgetConfig).where(WidgetConfig.organization_id == organization_id))
    if widget is None:
        widget = WidgetConfig(
            organization_id=organization_id,
            public_id=uuid.uuid4().hex,
            allowed_domains=list(_LOCAL_ORIGINS),
            operating_mode="human_review",
            enabled=True,
        )
        db.add(widget)
        db.flush()
        return widget
    domains = [item for item in widget.allowed_domains if isinstance(item, str)]
    for origin in _LOCAL_ORIGINS:
        if origin not in domains:
            domains.append(origin)
    widget.allowed_domains = domains
    widget.enabled = True
    db.flush()
    return widget


def _draft_body(draft: dict[str, object]) -> str | None:
    raw = draft.get("response")
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    body = parsed.get("body") if isinstance(parsed, dict) else None
    if not isinstance(body, str) or not body.strip():
        return None
    return body.strip()[:10000]


def _free_slot(db: Session, organization_id: uuid.UUID, connection: Any) -> tuple[datetime, datetime] | None:
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=3)
    calendar = WorkspaceCalendar()
    for offset in range(6):
        slot_start = start + timedelta(hours=offset)
        slot_end = slot_start + timedelta(minutes=30)
        google_free = available(connection, slot_start, slot_end)
        if google_free and calendar.available(db, organization_id, slot_start, slot_end):
            return slot_start, slot_end
    return None


def _mark_embedding(db: Session, organization_id: uuid.UUID, *, verified: bool, detail: str) -> None:
    record = _integration(db, organization_id, IntegrationType.embedding)
    if record is None:
        return
    record.verified_at = datetime.now(UTC) if verified else None
    record.verification_detail = detail[:500]
    record.status = IntegrationStatus.configured if verified else IntegrationStatus.verification_failed


def _integration(db: Session, organization_id: uuid.UUID, kind: IntegrationType) -> IntegrationConfig | None:
    return db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == organization_id,
            IntegrationConfig.integration_type == kind,
        )
    )


def _smtp_login(record: IntegrationConfig) -> tuple[str | None, str | None]:
    raw = open_credentials(record)
    if not raw:
        return None, None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    username = payload.get("username")
    password = payload.get("password")
    return (
        username if isinstance(username, str) and username else None,
        password if isinstance(password, str) and password else None,
    )


def _swap_public_api(value: str | None) -> str | None:
    import os

    previous = os.environ.get("ATLAS_PUBLIC_API_URL")
    if value is None:
        os.environ.pop("ATLAS_PUBLIC_API_URL", None)
    else:
        os.environ["ATLAS_PUBLIC_API_URL"] = value
    get_settings.cache_clear()
    return previous


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class _LeadCallback(BaseHTTPRequestHandler):
    engine: Any = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/health":
            self.send_response(404)
            self.end_headers()
            return
        body = b"harbor-listener"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/v1/hooks/lead-processed":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(min(length, 1_000_000))
        from app.domains.automation.hooks import accept_lead_processed

        with Session(self.engine) as db:
            try:
                code, payload = accept_lead_processed(db, self.headers, body)
            except AppError as exc:
                code = exc.status_code
                payload = {"error": {"code": exc.code}}
        encoded = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return
