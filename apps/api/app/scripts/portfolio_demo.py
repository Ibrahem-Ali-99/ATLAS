"""Provision fictional Atlas Demo records in an isolated database.

The command writes only a database named atlas_portfolio. It refuses the
development database, production, a public demo, live providers, and the
active upload directory. It does not print passwords or store credentials.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.config import Settings, get_settings
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, ApprovalStatus
from app.domains.approvals.service import create_approval
from app.domains.assistant.models import Conversation, Message, MessageRole
from app.domains.automation.models import (
    BookingStatus,
    CalendarBooking,
    ExecutionIntent,
    IntentStatus,
    WorkflowDefinition,
    WorkflowKind,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTask,
)
from app.domains.campaigns.models import Campaign, CustomerSegment, MarketingConsent
from app.domains.crm.models import (
    Company,
    Contact,
    Inquiry,
    Interaction,
    InteractionKind,
    Lead,
    LeadStatus,
    Opportunity,
    PipelineStage,
)
from app.domains.crm.service import (
    add_interaction,
    create_company,
    create_contact,
    create_inquiry,
    create_lead,
)
from app.domains.identity.models import Organization, User
from app.domains.identity.service import normalize_email
from app.domains.inbox.models import InboxConversation, InboxMessage, InboxStatus
from app.domains.knowledge.models import Document, DocumentStatus
from app.domains.provenance.origin import Origin
from app.scripts.seed import SeedSettings, seed_identity

PORTFOLIO_DATABASE = "atlas_portfolio"
KNOWLEDGE_NAME = "bonded-warehousing-overview.txt"
KNOWLEDGE_TEXT = (
    "Harbor & Co. service note\n\n"
    "Bonded warehousing is available at the north pier yard.\n"
    "Cold storage for the third quarter is confirmed for existing customers.\n"
    "A written service sheet is issued after a person reviews the inquiry.\n"
)
VISIT_SUBJECT = "Schedule a bonded-yard visit"
WORKFLOW_SLUG = "qualified-lead-follow-up"
WORKFLOW_KEY = hashlib.sha256(b"atlas-portfolio-harbor-workflow").hexdigest()
APPOINTMENT_KEY = hashlib.sha256(b"atlas-portfolio-harbor-appointment").hexdigest()
VISIT_START = datetime(2027, 3, 18, 15, 0, tzinfo=UTC)
VISIT_END = datetime(2027, 3, 18, 15, 30, tzinfo=UTC)


def database_name(url: str) -> str:
    return urlparse(url).path.rsplit("/", 1)[-1].split("?", 1)[0]


def assert_portfolio_target(url: str) -> str:
    if database_name(url) != PORTFOLIO_DATABASE:
        raise RuntimeError("Portfolio demo provisioning only writes the atlas_portfolio database.")
    return url


def assert_sandbox(settings: Settings) -> None:
    blocked: list[str] = []
    if settings.environment == "production":
        blocked.append("production")
    if settings.public_demo:
        blocked.append("a public demo")
    if settings.email_mode != "sandbox" or settings.email_live_enabled:
        blocked.append("live email")
    if settings.campaign_live_enabled:
        blocked.append("live campaigns")
    if settings.whatsapp_live_enabled:
        blocked.append("live WhatsApp")
    if settings.n8n_lead_webhook_url.strip():
        blocked.append("an n8n URL")
    if settings.llm_provider != "double" or settings.llm_api_key.strip():
        blocked.append("a paid chat model")
    if settings.embedding_provider != "double" or settings.embedding_api_key.strip():
        blocked.append("paid embeddings")
    if settings.billing_provider != "sandbox" or settings.stripe_secret_key.strip():
        blocked.append("a payment provider")
    if settings.google_calendar_client_secret.strip():
        blocked.append("a Google Calendar client secret")
    if blocked:
        raise RuntimeError("Portfolio demo provisioning refuses " + ", ".join(blocked) + ".")


def assert_portfolio_storage(path: Path, live: Path) -> Path:
    if not str(path).strip():
        raise RuntimeError(
            "Set ATLAS_PORTFOLIO_STORAGE_DIR to a directory outside the active upload store."
        )
    resolved = path.expanduser().resolve()
    live_resolved = live.expanduser().resolve()
    if resolved == live_resolved or resolved.is_relative_to(live_resolved):
        raise RuntimeError(
            "Portfolio documents must use a directory outside the active upload store."
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def populate_portfolio(db: Session, settings: SeedSettings, storage_dir: Path) -> None:
    seed_identity(db, settings)
    atlas = _organization(db, "atlas-demo")
    _organization(db, "northwind")
    admin = _user(db, str(settings.seed_admin_email))
    staff = _user(db, str(settings.seed_staff_email))
    harbor = _named(db, Company, atlas.id, Company.name, "Harbor & Co.")
    mina = _named(db, Contact, atlas.id, Contact.full_name, "Mina Patel")
    lead = _named(db, Lead, atlas.id, Lead.title, "North pier expansion")
    if harbor is None or mina is None or lead is None:
        raise RuntimeError("The portfolio seed did not create the Harbor & Co. records.")
    _extra_crm(db, atlas, admin, harbor, mina, lead)
    _inbox(db, atlas, staff, mina, lead)
    _knowledge(db, atlas, admin, storage_dir)
    _workflow(db, atlas, admin, lead, mina)
    _campaign(db, atlas, mina)
    _conversation(db, atlas, admin)
    _decisions(db, atlas, admin, lead)
    db.commit()


def main() -> int:
    if os.environ.get("ATLAS_PORTFOLIO_DEMO") != "apply":
        print(
            "Set ATLAS_PORTFOLIO_DEMO=apply to provision the isolated demo.",
            file=sys.stderr,
        )
        return 1
    try:
        url = assert_portfolio_target(os.environ.get("ATLAS_PORTFOLIO_DATABASE_URL", ""))
        settings = get_settings()
        assert_sandbox(settings)
        storage = assert_portfolio_storage(
            Path(os.environ.get("ATLAS_PORTFOLIO_STORAGE_DIR", "")),
            settings.upload_storage_dir,
        )
        seed = SeedSettings()
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        print(
            f"The portfolio database is not reachable ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    with Session(engine) as db:
        populate_portfolio(db, seed, storage)
    print("Portfolio demo records are in the atlas_portfolio database.")
    print("Passwords were not printed. No integration credential was stored.")
    print(f"- Atlas Demo: {seed.seed_admin_email} (admin), {seed.seed_staff_email} (staff)")
    print(f"- Northwind: {seed.seed_outsider_email} (admin)")
    print("In the workspace, choose Demo or All records.")
    return 0


def _organization(db: Session, slug: str) -> Organization:
    row = db.scalar(select(Organization).where(Organization.slug == slug))
    if row is None:
        raise RuntimeError(f"The portfolio seed did not create {slug}.")
    return row


def _user(db: Session, email: str) -> User:
    row = db.scalar(select(User).where(User.email == normalize_email(email)))
    if row is None:
        raise RuntimeError("The portfolio seed did not create the expected user.")
    return row


def _named[T](
    db: Session,
    model: type[T],
    organization_id: object,
    column: InstrumentedAttribute[str],
    value: str,
) -> T | None:
    table = cast(Any, model)
    return db.scalar(
        select(model).where(table.organization_id == organization_id, column == value)
    )


def _extra_crm(
    db: Session,
    atlas: Organization,
    admin: User,
    harbor: Company,
    mina: Contact,
    lead: Lead,
) -> None:
    for index, status in enumerate(LeadStatus):
        if (
            db.scalar(
                select(PipelineStage).where(
                    PipelineStage.organization_id == atlas.id,
                    PipelineStage.key == status.value,
                )
            )
            is None
        ):
            db.add(
                PipelineStage(
                    organization_id=atlas.id,
                    key=status.value,
                    label=status.value.replace("_", " ").title(),
                    position=index,
                    probability=1.0 if status is LeadStatus.won else 0.0,
                )
            )
    db.commit()
    if _named(db, Company, atlas.id, Company.name, "Lumen Freight") is None:
        lumen = create_company(
            db,
            atlas.id,
            {
                "name": "Lumen Freight",
                "website": "https://lumen.example",
                "industry": "Freight forwarding",
                "notes": "Fictional coastal carrier used only in the portfolio demo.",
                "origin": Origin.demo,
            },
        )
        jonah = create_contact(
            db,
            atlas.id,
            {
                "company_id": lumen.id,
                "full_name": "Jonah Ellis",
                "email": "jonah.ellis@lumen.example",
                "phone": "+1-555-0148",
                "title": "Network planner",
                "origin": Origin.demo,
            },
        )
        create_lead(
            db,
            atlas.id,
            admin.id,
            {
                "title": "Coastal relay inquiry",
                "status": LeadStatus.new,
                "source": "Website chat",
                "notes": "Jonah asked for a written quote on coastal relay capacity.",
                "company_id": lumen.id,
                "contact_id": jonah.id,
                "owner_user_id": admin.id,
                "origin": Origin.demo,
            },
        )
    if _named(db, Opportunity, atlas.id, Opportunity.title, "North pier bonded capacity") is None:
        db.add(
            Opportunity(
                organization_id=atlas.id,
                title="North pier bonded capacity",
                value=48000,
                currency="USD",
                expected_close_date=datetime(2027, 3, 31, tzinfo=UTC),
                owner_user_id=admin.id,
                company_id=harbor.id,
                contact_id=mina.id,
                lead_id=lead.id,
                stage=LeadStatus.qualified.value,
            )
        )
        db.commit()
    if (
        db.scalar(
            select(Interaction).where(
                Interaction.lead_id == lead.id,
                Interaction.body == "Portfolio demo recorded a discovery note.",
            )
        )
        is None
    ):
        add_interaction(
            db,
            atlas.id,
            lead.id,
            admin.id,
            {
                "kind": InteractionKind.note,
                "body": "Portfolio demo recorded a discovery note.",
                "origin": Origin.demo,
            },
        )
    _task(
        db,
        atlas,
        lead,
        mina,
        admin,
        title="Send the bonded warehousing service sheet",
        status="open",
        priority="high",
    )
    _task(
        db,
        atlas,
        lead,
        mina,
        admin,
        title="Confirm the north pier visit",
        status="completed",
        priority="normal",
    )


def _task(
    db: Session,
    atlas: Organization,
    lead: Lead,
    mina: Contact,
    admin: User,
    *,
    title: str,
    status: str,
    priority: str,
) -> None:
    if _named(db, WorkflowTask, atlas.id, WorkflowTask.title, title) is not None:
        return
    db.add(
        WorkflowTask(
            organization_id=atlas.id,
            lead_id=lead.id,
            contact_id=mina.id,
            assignee_user_id=admin.id,
            title=title,
            description="Fictional Harbor follow-up. Creating this task sends nothing.",
            due_at=datetime(2027, 3, 12, tzinfo=UTC),
            status=status,
            priority=priority,
            source="manual",
        )
    )
    db.commit()


def _inbox(db: Session, atlas: Organization, staff: User, mina: Contact, lead: Lead) -> None:
    email = _conversation_row(
        db,
        atlas,
        staff,
        mina,
        lead,
        subject="Cold storage for the north pier",
        channel="email",
    )
    _message(
        db,
        atlas,
        email,
        sender="mina.patel@harbor.example",
        recipient="inbox@atlas-demo.example",
        body="Could you confirm bonded and cold storage at the north pier yard?",
        direction="inbound",
        channel="email",
        delivery_status="received",
        provider_message_id="portfolio-harbor-email-1",
    )
    _message(
        db,
        atlas,
        email,
        sender="draft",
        recipient="mina.patel@harbor.example",
        body="Draft reply for review. This portfolio record was not sent.",
        direction="outbound",
        channel="email",
        delivery_status="draft",
        provider_message_id="portfolio-harbor-email-draft",
    )
    chat = _conversation_row(
        db,
        atlas,
        staff,
        mina,
        lead,
        subject="Website chat: bonded yard visit",
        channel="webchat",
    )
    _message(
        db,
        atlas,
        chat,
        sender="visitor",
        recipient="atlas-demo",
        body="I would like to visit the bonded yard next quarter.",
        direction="inbound",
        channel="webchat",
        delivery_status="received",
        provider_message_id="portfolio-harbor-webchat-1",
    )


def _conversation_row(
    db: Session,
    atlas: Organization,
    staff: User,
    mina: Contact,
    lead: Lead,
    *,
    subject: str,
    channel: str,
) -> InboxConversation:
    existing = _named(db, InboxConversation, atlas.id, InboxConversation.subject, subject)
    if existing is not None:
        return existing
    row = InboxConversation(
        organization_id=atlas.id,
        contact_id=mina.id,
        lead_id=lead.id,
        subject=subject,
        channel=channel,
        status=InboxStatus.open,
        assigned_to=staff.id,
        unread_count=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _message(
    db: Session, atlas: Organization, conversation: InboxConversation, **values: str
) -> None:
    if (
        db.scalar(
            select(InboxMessage).where(
                InboxMessage.organization_id == atlas.id,
                InboxMessage.provider_message_id == values["provider_message_id"],
            )
        )
        is not None
    ):
        return
    db.add(
        InboxMessage(
            organization_id=atlas.id,
            conversation_id=conversation.id,
            **values,
        )
    )
    db.commit()


def _knowledge(db: Session, atlas: Organization, admin: User, storage_dir: Path) -> None:
    existing = _named(db, Document, atlas.id, Document.title, "Bonded warehousing overview")
    payload = KNOWLEDGE_TEXT.encode()
    if existing is not None:
        return
    document = Document(
        organization_id=atlas.id,
        uploaded_by=admin.id,
        title="Bonded warehousing overview",
        filename=KNOWLEDGE_NAME,
        media_type="text/plain",
        byte_size=len(payload),
        storage_path="",
        status=DocumentStatus.pending,
        origin=Origin.demo,
        content_sha256=hashlib.sha256(payload).hexdigest(),
    )
    db.add(document)
    db.flush()
    path = (storage_dir / str(atlas.id) / str(document.id)).resolve()
    if not path.is_relative_to(storage_dir.resolve()):
        raise RuntimeError("The portfolio document path left the selected directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    document.storage_path = str(path)
    db.commit()


def _workflow(db: Session, atlas: Organization, admin: User, lead: Lead, mina: Contact) -> None:
    definition = db.scalar(
        select(WorkflowDefinition).where(
            WorkflowDefinition.organization_id == atlas.id,
            WorkflowDefinition.slug == WORKFLOW_SLUG,
        )
    )
    if definition is None:
        definition = WorkflowDefinition(
            organization_id=atlas.id,
            slug=WORKFLOW_SLUG,
            name="Qualified lead follow-up",
            description="Fictional definition. It is inactive, so it does not dispatch.",
            version=1,
            active=False,
            definition={
                "trigger": "lead_created",
                "condition_mode": "all",
                "conditions": [
                    {"field": "lead_status", "operator": "equals", "value": "qualified"}
                ],
                "actions": [
                    {"type": "require_approval"},
                    {"type": "create_task", "title": "Send the service sheet"},
                ],
                "otherwise_actions": [],
            },
            created_by=admin.id,
        )
        db.add(definition)
        db.commit()
        db.refresh(definition)
    if db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == WORKFLOW_KEY)) is None:
        db.add(
            WorkflowRun(
                organization_id=atlas.id,
                kind=WorkflowKind.follow_up,
                status=WorkflowStatus.completed,
                idempotency_key=WORKFLOW_KEY,
                lead_id=lead.id,
                origin=Origin.demo,
                payload={
                    "workflow_definition_id": str(definition.id),
                    "outcome": "completed",
                    "manual": True,
                    "summary": "Historical demonstration run. No message was sent.",
                    "steps": [
                        {"type": "require_approval", "status": "completed"},
                        {
                            "type": "create_task",
                            "title": "Send the service sheet",
                            "status": "completed",
                        },
                    ],
                },
            )
        )
        db.commit()
    if _named(db, WorkflowTask, atlas.id, WorkflowTask.title, "Prepare the yard agenda") is None:
        db.add(
            WorkflowTask(
                organization_id=atlas.id,
                lead_id=lead.id,
                contact_id=mina.id,
                assignee_user_id=admin.id,
                title="Prepare the yard agenda",
                description="Created for the historical demonstration run.",
                status="completed",
                priority="normal",
                source="workflow",
            )
        )
        db.commit()


def _campaign(db: Session, atlas: Organization, mina: Contact) -> None:
    segment = db.scalar(
        select(CustomerSegment).where(
            CustomerSegment.organization_id == atlas.id,
            CustomerSegment.name == "Harbor operations contacts",
        )
    )
    if segment is None:
        segment = CustomerSegment(
            organization_id=atlas.id,
            name="Harbor operations contacts",
            definition={
                "logic": "and",
                "conditions": [
                    {
                        "field": "contact_email",
                        "operator": "eq",
                        "value": "mina.patel@harbor.example",
                    }
                ],
            },
        )
        db.add(segment)
        db.commit()
        db.refresh(segment)
    if (
        db.scalar(
            select(MarketingConsent).where(
                MarketingConsent.organization_id == atlas.id,
                MarketingConsent.contact_id == mina.id,
            )
        )
        is None
    ):
        db.add(
            MarketingConsent(
                organization_id=atlas.id,
                contact_id=mina.id,
                status="granted",
                source="portfolio-demo",
                consented_at=datetime(2026, 11, 1, tzinfo=UTC),
            )
        )
        db.commit()
    if _named(db, Campaign, atlas.id, Campaign.name, "Q3 cold-storage briefing") is None:
        db.add(
            Campaign(
                organization_id=atlas.id,
                segment_id=segment.id,
                name="Q3 cold-storage briefing",
                description="Draft only. The portfolio demo does not queue delivery.",
                channel="email",
                status="draft",
                subject="Cold storage availability",
                body="This draft is stored for review. It has not been scheduled.",
                delivery_mode="sandbox",
            )
        )
        db.commit()


def _conversation(db: Session, atlas: Organization, admin: User) -> None:
    existing = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == atlas.id,
            Conversation.user_id == admin.id,
            Conversation.title == "Bonded yard capacity",
        )
    )
    if existing is not None:
        return
    conversation = Conversation(
        organization_id=atlas.id,
        user_id=admin.id,
        title="Bonded yard capacity",
    )
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            Message(
                conversation_id=conversation.id,
                organization_id=atlas.id,
                role=MessageRole.user,
                content="Does Harbor & Co. have cold storage this quarter?",
            ),
            Message(
                conversation_id=conversation.id,
                organization_id=atlas.id,
                role=MessageRole.assistant,
                content=(
                    "This demonstration conversation is stored for Harbor & Co. "
                    "A sourced answer is available after the bonded warehousing note is indexed. "
                    "The assistant cites a retrieved passage or refuses when nothing matches."
                ),
            ),
        ]
    )
    db.commit()


def _decisions(db: Session, atlas: Organization, admin: User, lead: Lead) -> None:
    inquiry = db.scalar(
        select(Inquiry).where(
            Inquiry.organization_id == atlas.id,
            Inquiry.subject == VISIT_SUBJECT,
        )
    )
    if inquiry is None:
        inquiry = create_inquiry(
            db,
            atlas.id,
            {
                "subject": VISIT_SUBJECT,
                "body": "Mina asked to walk the bonded yard before the third quarter.",
                "company_id": lead.company_id,
                "lead_id": lead.id,
                "origin": Origin.demo,
            },
        )
    run = db.scalar(select(AgentRun).where(AgentRun.inquiry_id == inquiry.id))
    if run is not None:
        return
    run = AgentRun(
        organization_id=atlas.id,
        inquiry_id=inquiry.id,
        started_by=admin.id,
        status=RunStatus.completed,
        origin=Origin.demo,
        finished_at=datetime(2027, 3, 1, tzinfo=UTC),
    )
    db.add(run)
    db.flush()
    rejected = create_approval(
        db,
        organization_id=atlas.id,
        run_id=run.id,
        requested_by=admin.id,
        action_type=ActionType.prepare_customer_response,
        payload={
            "subject": "Bonded warehousing",
            "recipient": "mina.patel@harbor.example",
            "body": "Thank you. A person will send the service sheet after review.",
        },
        position=0,
        commit=False,
    )
    rejected.status = ApprovalStatus.rejected
    rejected.decided_by = admin.id
    rejected.decided_at = datetime(2027, 3, 1, tzinfo=UTC)
    rejected.decision_note = "Demonstration record. No message was sent."
    approved = create_approval(
        db,
        organization_id=atlas.id,
        run_id=run.id,
        requested_by=admin.id,
        action_type=ActionType.request_appointment,
        payload={
            "body": "Visit the north pier yard to review bonded storage.",
            "starts_at": VISIT_START.isoformat(),
            "ends_at": VISIT_END.isoformat(),
            "lead_id": str(lead.id),
        },
        position=1,
        commit=False,
    )
    approved.status = ApprovalStatus.executed
    approved.decided_by = admin.id
    approved.decided_at = datetime(2027, 3, 1, tzinfo=UTC)
    approved.executed_at = datetime(2027, 3, 1, tzinfo=UTC)
    approved.decision_note = "Demonstration record. The booking stays inside ATLAS."
    intent = ExecutionIntent(
        organization_id=atlas.id,
        approval_id=approved.id,
        action_type=ActionType.request_appointment,
        payload=approved.payload,
        idempotency_key=APPOINTMENT_KEY,
        status=IntentStatus.succeeded,
        origin=Origin.demo,
        result={"provider": "simulation"},
    )
    db.add(intent)
    db.flush()
    db.add(
        CalendarBooking(
            organization_id=atlas.id,
            lead_id=lead.id,
            intent_id=intent.id,
            starts_at=VISIT_START,
            ends_at=VISIT_END,
            status=BookingStatus.booked,
            provider="simulation",
            origin=Origin.demo,
        )
    )
    db.commit()


if __name__ == "__main__":
    raise SystemExit(main())
