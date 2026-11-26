"""Persist the Harbor & Co. demonstration as ordinary application rows.

Rows that have an origin are marked demo. Campaign deliveries stay on the
simulated status: nothing is queued and no provider is called. Workflow
definitions stay inactive so a free-plan visitor can still activate two.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType, Approval, ApprovalStatus
from app.domains.approvals.service import payload_hash
from app.domains.assistant.models import (
    Conversation,
    Message,
    MessageRole,
    MessageSource,
    SourceKind,
)
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
from app.domains.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignSuppression,
    CustomerSegment,
    MarketingConsent,
)
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
from app.domains.demo.harbor_catalog import (
    APPOINTMENT_COUNT,
    COMPANIES,
    CONTACTS,
    CONVERSATION_COUNT,
    DOCUMENTS,
    EVALUATIONS,
    LEAD_COUNT,
    LEAD_NOTE,
    LEAD_STATUSES,
    OPPORTUNITY_COUNT,
    OPPORTUNITY_STAGES,
    SEEDED_ASSISTANT_CONTENT,
    SEEDED_CONVERSATION_TITLE,
    TASK_COUNT,
    WORKFLOWS,
    lead_title,
    moment,
)
from app.domains.identity.models import Organization, User
from app.domains.inbox.models import InboxConversation, InboxMessage, InboxStatus
from app.domains.knowledge.models import Chunk, Document, DocumentStatus, EvaluationQuestion
from app.domains.knowledge.vectors import store_chunk_embedding
from app.domains.provenance.origin import Origin
from app.integrations.doubles import hash_embedding

_CHANNELS = ("email", "webchat", "whatsapp")
_INBOX_STATUSES = (InboxStatus.open, InboxStatus.pending, InboxStatus.resolved)


def populate(
    db: Session,
    organization: Organization,
    user: User,
    *,
    storage_root: Path | None = None,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    companies = _companies(db, organization, now)
    contacts = _contacts(db, organization, companies, now)
    _stages(db, organization)
    leads = _leads(db, organization, user, companies, contacts, now)
    _opportunities(db, organization, user, leads, now)
    inquiries = _inquiries(db, organization, leads, now)
    _interactions(db, organization, user, leads, now)
    _inbox(db, organization, user, contacts, leads, now)
    document, chunk = _knowledge(db, organization, user, now, storage_root)
    _evaluations(db, organization, user)
    definitions, runs = _workflows(db, organization, user, leads, now)
    _tasks(db, organization, user, contacts, leads, runs, now)
    _campaigns(db, organization, contacts, now)
    _appointments(db, organization, user, leads, inquiries, now)
    _pending_decisions(db, organization, user, leads[0], inquiries[0], now)
    _assistant(db, organization, user, document, chunk, now)
    db.flush()
    db.execute(
        update(Chunk)
        .where(Chunk.organization_id == organization.id)
        .values(search_vector=func.to_tsvector("english", Chunk.content))
    )
    db.commit()


def _stamp(record: Any, when: datetime) -> Any:
    if hasattr(record, "created_at"):
        record.created_at = when
    if hasattr(record, "updated_at"):
        record.updated_at = when
    return record


def _key(organization: Organization, label: str) -> str:
    return hashlib.sha256(f"harbor:{organization.id}:{label}".encode()).hexdigest()


def _companies(db: Session, organization: Organization, now: datetime) -> list[Company]:
    rows = []
    for index, (name, website, industry) in enumerate(COMPANIES):
        row = _stamp(
            Company(
                organization_id=organization.id,
                name=name,
                website=website,
                industry=industry,
                notes="Fictional demonstration account. Changes stay in this workspace.",
                origin=Origin.demo,
            ),
            moment(index, len(COMPANIES), now=now),
        )
        rows.append(row)
    db.add_all(rows)
    db.flush()
    return rows


def _contacts(
    db: Session, organization: Organization, companies: list[Company], now: datetime
) -> list[Contact]:
    rows = []
    for index, (name, title, local) in enumerate(CONTACTS):
        company = companies[index // 2]
        domain = company.website.removeprefix("https://") if company.website else "example"
        phone = "+1-555-0108" if index == 0 else f"+1-555-{2100 + index:04d}"
        rows.append(
            _stamp(
                Contact(
                    organization_id=organization.id,
                    company_id=company.id,
                    full_name=name,
                    email=f"{local}@{domain}",
                    phone=phone,
                    title=title,
                    origin=Origin.demo,
                ),
                moment(index, len(CONTACTS), now=now),
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def _stages(db: Session, organization: Organization) -> None:
    for index, status in enumerate(LeadStatus):
        db.add(
            PipelineStage(
                organization_id=organization.id,
                key=status.value,
                label=status.value.replace("_", " ").title(),
                position=index,
                probability=1.0 if status is LeadStatus.won else 0.0,
            )
        )
    db.flush()


def _leads(
    db: Session,
    organization: Organization,
    user: User,
    companies: list[Company],
    contacts: list[Contact],
    now: datetime,
) -> list[Lead]:
    rows = []
    for index in range(LEAD_COUNT):
        contact = contacts[index % len(contacts)]
        rows.append(
            _stamp(
                Lead(
                    organization_id=organization.id,
                    company_id=contact.company_id,
                    contact_id=contact.id,
                    owner_user_id=user.id,
                    title=lead_title(index),
                    status=LeadStatus(LEAD_STATUSES[index]),
                    source=("Website", "Referral", "Trade show", "Email")[index % 4],
                    notes="Mina asked about bonded and cold storage at the north pier yard."
                    if index == 0
                    else f"Fictional lot for {companies[index % len(companies)].name}.",
                    origin=Origin.demo,
                ),
                moment(index, LEAD_COUNT, now=now),
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def _opportunities(
    db: Session,
    organization: Organization,
    user: User,
    leads: list[Lead],
    now: datetime,
) -> None:
    rows = []
    for index in range(OPPORTUNITY_COUNT):
        lead = leads[index]
        stage = OPPORTUNITY_STAGES[index]
        currency = "EUR" if index % 9 == 8 else "USD"
        value = 48000 if index == 0 else float(12000 + index * 900)
        title = "North pier bonded capacity" if index == 0 else f"Capacity for {lead.title}"
        rows.append(
            _stamp(
                Opportunity(
                    organization_id=organization.id,
                    title=title,
                    value=value,
                    currency=currency,
                    expected_close_date=now + timedelta(days=20 + index),
                    probability=1.0 if stage == "won" else 0.2,
                    owner_user_id=user.id,
                    company_id=lead.company_id,
                    contact_id=lead.contact_id,
                    lead_id=lead.id,
                    stage=stage,
                    loss_reason="The shipper kept the freight at origin."
                    if stage == "lost"
                    else None,
                ),
                moment(index, OPPORTUNITY_COUNT, now=now),
            )
        )
    db.add_all(rows)
    db.flush()


def _inquiries(
    db: Session, organization: Organization, leads: list[Lead], now: datetime
) -> list[Inquiry]:
    rows = []
    for index in range(CONVERSATION_COUNT):
        lead = leads[index]
        subject = (
            "Bonded warehousing at the north pier" if index == 0 else f"Yard request {index + 1}"
        )
        rows.append(
            _stamp(
                Inquiry(
                    organization_id=organization.id,
                    company_id=lead.company_id,
                    lead_id=lead.id,
                    subject=subject,
                    body="Please confirm the bay, the temperature, and the visit window.",
                    origin=Origin.demo,
                ),
                moment(index, CONVERSATION_COUNT, now=now),
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def _interactions(
    db: Session, organization: Organization, user: User, leads: list[Lead], now: datetime
) -> None:
    kinds = (InteractionKind.note, InteractionKind.call, InteractionKind.email)
    rows = []
    for index in range(20):
        rows.append(
            _stamp(
                Interaction(
                    organization_id=organization.id,
                    lead_id=leads[index].id,
                    author_user_id=user.id,
                    kind=kinds[index % 3],
                    body="Demonstration note. No call was placed and no email was sent.",
                    origin=Origin.demo,
                ),
                moment(index, 20, now=now),
            )
        )
    db.add_all(rows)


def _inbox(
    db: Session,
    organization: Organization,
    user: User,
    contacts: list[Contact],
    leads: list[Lead],
    now: datetime,
) -> list[InboxConversation]:
    rows = []
    messages: list[InboxMessage] = []
    for index in range(CONVERSATION_COUNT):
        contact = contacts[index % len(contacts)]
        lead = leads[index]
        channel = _CHANNELS[index % len(_CHANNELS)]
        subject = "Cold storage for the north pier" if index == 0 else f"{lead.title} · {channel}"
        when = moment(index, CONVERSATION_COUNT, now=now)
        conversation = _stamp(
            InboxConversation(
                organization_id=organization.id,
                contact_id=contact.id,
                lead_id=lead.id,
                subject=subject[:200],
                channel=channel,
                status=_INBOX_STATUSES[index % len(_INBOX_STATUSES)],
                assigned_to=user.id,
                unread_count=1 if index % 3 == 0 else 0,
            ),
            when,
        )
        rows.append(conversation)
        db.add(conversation)
    db.flush()
    for index, conversation in enumerate(rows):
        contact = contacts[index % len(contacts)]
        when = moment(index, CONVERSATION_COUNT, now=now)
        question = (
            "Could you confirm bonded and cold storage at the north pier yard?"
            if index == 0
            else f"Can the yard take the {leads[index].title.lower()} lot next month?"
        )
        messages.append(
            _stamp(
                InboxMessage(
                    organization_id=organization.id,
                    conversation_id=conversation.id,
                    sender=contact.email or "visitor",
                    recipient="inbox@harbor.example",
                    body=question,
                    direction="inbound",
                    channel=conversation.channel,
                    delivery_status="received",
                    provider_message_id=f"harbor-{organization.id}-in-{index}",
                ),
                when,
            )
        )
        messages.append(
            _stamp(
                InboxMessage(
                    organization_id=organization.id,
                    conversation_id=conversation.id,
                    sender="draft",
                    recipient=contact.email or "visitor",
                    body="Draft reply for review. This demonstration message was not sent.",
                    direction="outbound",
                    channel=conversation.channel,
                    delivery_status="draft",
                    provider_message_id=f"harbor-{organization.id}-draft-{index}",
                ),
                when + timedelta(minutes=5),
            )
        )
        messages.append(
            _stamp(
                InboxMessage(
                    organization_id=organization.id,
                    conversation_id=conversation.id,
                    sender=contact.email or "visitor",
                    recipient="inbox@harbor.example",
                    body="A second note from the same thread. No message has left this workspace.",
                    direction="inbound",
                    channel=conversation.channel,
                    delivery_status="received",
                    provider_message_id=f"harbor-{organization.id}-follow-{index}",
                ),
                when + timedelta(minutes=20),
            )
        )
    db.add_all(messages)
    return rows


def _knowledge(
    db: Session,
    organization: Organization,
    user: User,
    now: datetime,
    storage_root: Path | None,
) -> tuple[Document, Chunk]:
    settings = get_settings()
    root = Path(storage_root or settings.upload_storage_dir).expanduser().resolve()
    first_document: Document | None = None
    first_chunk: Chunk | None = None
    for index, (title, filename, body) in enumerate(DOCUMENTS):
        payload = body.encode()
        document = _stamp(
            Document(
                organization_id=organization.id,
                uploaded_by=user.id,
                title=title,
                filename=filename,
                media_type="text/plain",
                byte_size=len(payload),
                storage_path="",
                status=DocumentStatus.ready,
                origin=Origin.demo,
                content_sha256=hashlib.sha256(payload).hexdigest(),
            ),
            moment(index, len(DOCUMENTS), now=now),
        )
        db.add(document)
        db.flush()
        path = (root / str(organization.id) / str(document.id)).resolve()
        if not path.is_relative_to(root):
            raise AppError(500, "demo_limited", "The demonstration document path is invalid.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        document.storage_path = str(path)
        chunk = Chunk(
            organization_id=organization.id,
            document_id=document.id,
            chunk_index=0,
            page_number=1,
            content=body,
        )
        store_chunk_embedding(chunk, hash_embedding(body, settings.embedding_dimensions), settings)
        db.add(chunk)
        if index == 0:
            first_document = document
            first_chunk = chunk
    db.flush()
    if first_document is None or first_chunk is None:
        raise AppError(500, "demo_limited", "The demonstration library was not stored.")
    return first_document, first_chunk


def _evaluations(db: Session, organization: Organization, user: User) -> None:
    for question, scenario, behavior, evidence in EVALUATIONS:
        db.add(
            EvaluationQuestion(
                organization_id=organization.id,
                created_by=user.id,
                question=question,
                scenario=scenario,
                expected_behavior=behavior,
                expected_evidence=list(evidence),
            )
        )


def _workflows(
    db: Session,
    organization: Organization,
    user: User,
    leads: list[Lead],
    now: datetime,
) -> tuple[list[WorkflowDefinition], list[WorkflowRun]]:
    definitions: list[WorkflowDefinition] = []
    runs: list[WorkflowRun] = []
    for index, (slug, name, description, definition) in enumerate(WORKFLOWS):
        row = _stamp(
            WorkflowDefinition(
                organization_id=organization.id,
                slug=slug,
                name=name,
                description=description,
                version=1,
                active=False,
                definition=definition,
                created_by=user.id,
            ),
            moment(index, len(WORKFLOWS), now=now),
        )
        definitions.append(row)
        db.add(row)
    db.flush()
    for index, definition in enumerate(definitions):
        for copy in range(2):
            lead = leads[(index * 2 + copy) % len(leads)]
            branch = "matched" if copy == 0 else "otherwise"
            task_status = "completed" if index == 0 and copy == 0 else "simulated"
            run = _stamp(
                WorkflowRun(
                    organization_id=organization.id,
                    kind=WorkflowKind.follow_up,
                    status=WorkflowStatus.completed,
                    idempotency_key=_key(organization, f"workflow:{definition.slug}:{copy}"),
                    lead_id=lead.id,
                    origin=Origin.demo,
                    payload={
                        "workflow_definition_id": str(definition.id),
                        "outcome": "completed",
                        "manual": True,
                        "branch": branch,
                        "summary": "Recorded demonstration run. No customer message was sent.",
                        "steps": [
                            {
                                "type": "condition",
                                "status": "matched" if branch == "matched" else "not_matched",
                            },
                            {
                                "type": "create_task",
                                "title": "Demonstration task",
                                "status": task_status,
                            },
                        ],
                    },
                ),
                moment(index * 2 + copy, len(WORKFLOWS) * 2, now=now),
            )
            runs.append(run)
    db.add_all(runs)
    db.flush()
    return definitions, runs


def _tasks(
    db: Session,
    organization: Organization,
    user: User,
    contacts: list[Contact],
    leads: list[Lead],
    runs: list[WorkflowRun],
    now: datetime,
) -> None:
    priorities = ("high", "normal", "low")
    statuses = ("open", "completed", "open", "cancelled")
    titles = (
        "Send the bonded service sheet",
        "Confirm the cold-room set point",
        "Check the packing list",
        "Book the Thursday visit window",
        "Recount the timber packs",
        "Review the shortage claim",
        "Prepare the quay checklist",
    )
    rows = []
    for index in range(TASK_COUNT):
        status = statuses[index % len(statuses)]
        due = now + timedelta(days=-5 if status == "open" and index % 2 == 0 else 12 + index)
        run = runs[0] if index == 0 else None
        rows.append(
            _stamp(
                WorkflowTask(
                    organization_id=organization.id,
                    workflow_run_id=run.id if run is not None else None,
                    lead_id=leads[index % len(leads)].id,
                    contact_id=contacts[index % len(contacts)].id,
                    assignee_user_id=user.id,
                    title=titles[index % len(titles)] if index else "Send the bonded service sheet",
                    description="Demonstration follow-up. Creating this task sends nothing.",
                    due_at=due,
                    status=status,
                    priority=priorities[index % len(priorities)],
                    source="workflow" if run is not None else "manual",
                ),
                moment(index, TASK_COUNT, now=now),
            )
        )
    db.add_all(rows)


def _campaigns(
    db: Session, organization: Organization, contacts: list[Contact], now: datetime
) -> None:
    mina = contacts[0]
    yard = contacts[:8]
    peak = contacts[8:14]
    suppressed = contacts[14]
    for contact in yard + peak:
        db.add(
            MarketingConsent(
                organization_id=organization.id,
                contact_id=contact.id,
                status="granted",
                source="demonstration",
                consented_at=now - timedelta(days=40),
            )
        )
    db.add(
        CampaignSuppression(
            organization_id=organization.id,
            email=suppressed.email or "suppressed@harbor.example",
            reason="unsubscribe",
            created_at=now - timedelta(days=30),
        )
    )
    draft_segment = CustomerSegment(
        organization_id=organization.id,
        name="Harbor operations contacts",
        definition={
            "logic": "and",
            "conditions": [
                {"field": "contact_email", "operator": "eq", "value": mina.email},
            ],
        },
    )
    yard_segment = _email_segment(organization, "Yard safety audience", yard)
    peak_segment = _email_segment(organization, "Peak season audience", peak)
    db.add_all([draft_segment, yard_segment, peak_segment])
    db.flush()
    draft = _stamp(
        Campaign(
            organization_id=organization.id,
            segment_id=draft_segment.id,
            name="Q3 cold-storage briefing",
            description="Draft only. A demonstration session cannot schedule delivery.",
            channel="email",
            status="draft",
            subject="Cold storage availability",
            body="This draft is stored for review. It has not been scheduled.",
            delivery_mode="sandbox",
        ),
        now - timedelta(days=2),
    )
    recorded = _stamp(
        Campaign(
            organization_id=organization.id,
            segment_id=yard_segment.id,
            name="Yard safety bulletin",
            description="Simulated delivery record. No message left this workspace.",
            channel="email",
            status="recorded",
            subject="Quay clothing and gate hours",
            body="Simulated bulletin. The provider was not called.",
            delivery_mode="sandbox",
            finished_at=now - timedelta(days=18),
        ),
        now - timedelta(days=20),
    )
    peak_campaign = _stamp(
        Campaign(
            organization_id=organization.id,
            segment_id=peak_segment.id,
            name="Peak season capacity note",
            description="Simulated delivery record. No message left this workspace.",
            channel="email",
            status="recorded",
            subject="Peak season bay availability",
            body="Simulated note. The provider was not called.",
            delivery_mode="sandbox",
            finished_at=now - timedelta(days=60),
        ),
        now - timedelta(days=70),
    )
    db.add_all([draft, recorded, peak_campaign])
    db.flush()
    db.add_all(
        [
            CampaignDelivery(campaign_id=recorded.id, email=contact.email or "", status="simulated")
            for contact in yard
            if contact.email
        ]
        + [
            CampaignDelivery(
                campaign_id=peak_campaign.id, email=contact.email or "", status="simulated"
            )
            for contact in peak
            if contact.email
        ]
    )


def _email_segment(
    organization: Organization, name: str, contacts: list[Contact]
) -> CustomerSegment:
    return CustomerSegment(
        organization_id=organization.id,
        name=name,
        definition={
            "logic": "or",
            "conditions": [
                {"field": "contact_email", "operator": "eq", "value": contact.email}
                for contact in contacts
                if contact.email
            ],
        },
    )


def _appointments(
    db: Session,
    organization: Organization,
    user: User,
    leads: list[Lead],
    inquiries: list[Inquiry],
    now: datetime,
) -> None:
    for index in range(APPOINTMENT_COUNT):
        lead = leads[index]
        when = moment(index, APPOINTMENT_COUNT, now=now)
        if index < 8:
            start = now - timedelta(days=40 - index, hours=-15)
            status = BookingStatus.booked
        elif index < 10:
            start = now - timedelta(days=15 - index)
            status = BookingStatus.cancelled
        else:
            start = now + timedelta(days=10 + index, hours=15)
            status = BookingStatus.booked
        start = start.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=30)
        run = AgentRun(
            organization_id=organization.id,
            inquiry_id=inquiries[index].id,
            started_by=user.id,
            status=RunStatus.completed,
            origin=Origin.demo,
            started_at=when,
            finished_at=when + timedelta(minutes=1),
        )
        db.add(run)
        db.flush()
        payload = {
            "lead_id": str(lead.id),
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "provider": "simulation",
            "summary": "Yard visit stored in ATLAS. No external calendar was called.",
        }
        approval = _stamp(
            Approval(
                organization_id=organization.id,
                run_id=run.id,
                requested_by=user.id,
                action_type=ActionType.request_appointment,
                position=0,
                payload=payload,
                payload_hash=payload_hash(payload),
                origin=Origin.demo,
                status=ApprovalStatus.executed,
                expires_at=when + timedelta(days=7),
                decided_by=user.id,
                decided_at=when,
                decision_note="Recorded in ATLAS. No external event was created.",
                executed_at=when,
                execution_result={
                    "provider": "simulation",
                    "provider_event_id": None,
                    "note": "Stored in ATLAS. No external calendar was called.",
                },
            ),
            when,
        )
        db.add(approval)
        db.flush()
        intent = ExecutionIntent(
            organization_id=organization.id,
            approval_id=approval.id,
            action_type=ActionType.request_appointment,
            payload=payload,
            idempotency_key=_key(organization, f"booking:{index}"),
            status=IntentStatus.succeeded,
            origin=Origin.demo,
            result={"provider": "simulation", "provider_event_id": None},
            created_at=when,
        )
        db.add(intent)
        db.flush()
        db.add(
            _stamp(
                CalendarBooking(
                    organization_id=organization.id,
                    lead_id=lead.id,
                    intent_id=intent.id,
                    starts_at=start,
                    ends_at=end,
                    status=status,
                    provider="simulation",
                    origin=Origin.demo,
                    provider_event_id=None,
                ),
                when,
            )
        )


def _pending_decisions(
    db: Session,
    organization: Organization,
    user: User,
    lead: Lead,
    inquiry: Inquiry,
    now: datetime,
) -> None:
    update_payload = {
        "lead_id": str(lead.id),
        "status": LeadStatus.qualified.value,
        "notes": LEAD_NOTE,
        "title": lead.title,
    }
    _pending(db, organization, user, inquiry, ActionType.update_lead, update_payload, now)
    message = {
        "lead_id": str(lead.id),
        "recipient": "mina.patel@harbor.example",
        "subject": "Bonded warehousing",
        "body": "Draft for review. This demonstration message was not sent.",
        "delivery_mode": "sandbox",
        "channel": "email",
        "contact_name": "Mina Patel",
        "company_name": "Harbor & Co.",
    }
    rates = {**message, "subject": "Cold storage rates"}
    _pending(db, organization, user, inquiry, ActionType.prepare_customer_response, message, now)
    _pending(db, organization, user, inquiry, ActionType.prepare_customer_response, rates, now)
    rejected_run = AgentRun(
        organization_id=organization.id,
        inquiry_id=inquiry.id,
        started_by=user.id,
        status=RunStatus.completed,
        origin=Origin.demo,
        started_at=now - timedelta(days=12),
        finished_at=now - timedelta(days=12),
    )
    db.add(rejected_run)
    db.flush()
    rejected_payload = {**message, "subject": "Rejected bonded reply"}
    db.add(
        _stamp(
            Approval(
                organization_id=organization.id,
                run_id=rejected_run.id,
                requested_by=user.id,
                action_type=ActionType.prepare_customer_response,
                position=0,
                payload=rejected_payload,
                payload_hash=payload_hash(rejected_payload),
                origin=Origin.demo,
                status=ApprovalStatus.rejected,
                expires_at=now + timedelta(days=7),
                decided_by=user.id,
                decided_at=now - timedelta(days=12),
                decision_note="No message was sent.",
            ),
            now - timedelta(days=12),
        )
    )


def _pending(
    db: Session,
    organization: Organization,
    user: User,
    inquiry: Inquiry,
    action: ActionType,
    payload: dict[str, Any],
    now: datetime,
) -> None:
    run = AgentRun(
        organization_id=organization.id,
        inquiry_id=inquiry.id,
        started_by=user.id,
        status=RunStatus.awaiting_approval,
        origin=Origin.demo,
        started_at=now,
    )
    db.add(run)
    db.flush()
    db.add(
        Approval(
            organization_id=organization.id,
            run_id=run.id,
            requested_by=user.id,
            action_type=action,
            position=0,
            payload=payload,
            payload_hash=payload_hash(payload),
            origin=Origin.demo,
            status=ApprovalStatus.pending,
            expires_at=now + timedelta(days=14),
        )
    )


def _assistant(
    db: Session,
    organization: Organization,
    user: User,
    document: Document,
    chunk: Chunk,
    now: datetime,
) -> None:
    conversation = Conversation(
        organization_id=organization.id,
        user_id=user.id,
        title=SEEDED_CONVERSATION_TITLE,
        created_at=now - timedelta(days=3),
        updated_at=now + timedelta(minutes=1),
    )
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            organization_id=organization.id,
            role=MessageRole.user,
            content="Is bonded warehousing available at the north pier?",
            created_at=now - timedelta(days=3),
        )
    )
    answer = Message(
        conversation_id=conversation.id,
        organization_id=organization.id,
        role=MessageRole.assistant,
        content=SEEDED_ASSISTANT_CONTENT,
        created_at=now - timedelta(days=3) + timedelta(seconds=5),
    )
    db.add(answer)
    db.flush()
    db.add(
        MessageSource(
            message_id=answer.id,
            organization_id=organization.id,
            kind=SourceKind.document,
            document_id=document.id,
            chunk_id=chunk.id,
            page_number=1,
            title=document.title,
            excerpt=SEEDED_ASSISTANT_CONTENT,
        )
    )
