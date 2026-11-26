"""Fictional Harbor & Co. rows for one visitor organization.

These rows use operational origin so the workspace lists show them.
The organization itself is the demonstration, and it is deleted with the session.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.assistant.models import (
    Conversation,
    Message,
    MessageRole,
    MessageSource,
    SourceKind,
)
from app.domains.automation.models import (
    WorkflowDefinition,
    WorkflowKind,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTask,
)
from app.domains.campaigns.models import Campaign, CustomerSegment, MarketingConsent
from app.domains.crm.models import InteractionKind, LeadStatus, Opportunity, PipelineStage
from app.domains.crm.service import (
    add_interaction,
    create_company,
    create_contact,
    create_inquiry,
    create_lead,
)
from app.domains.identity.models import Organization, User
from app.domains.inbox.models import InboxConversation, InboxMessage, InboxStatus
from app.domains.knowledge.models import Chunk, Document, DocumentStatus
from app.domains.knowledge.vectors import store_chunk_embedding
from app.domains.provenance.origin import Origin
from app.integrations.doubles import hash_embedding

KNOWLEDGE_TEXT = (
    "Harbor & Co. service note\n\n"
    "Bonded warehousing is available at the north pier yard.\n"
    "Cold storage for the third quarter is confirmed for existing customers.\n"
    "A written service sheet is issued after a person reviews the inquiry.\n"
)
KNOWLEDGE_TITLE = "Bonded warehousing overview"


def populate_visitor(db: Session, organization: Organization, user: User) -> None:
    harbor = create_company(
        db,
        organization.id,
        {
            "name": "Harbor & Co.",
            "website": "https://harbor.example",
            "industry": "Logistics",
            "notes": "Fictional demonstration account. Changes stay in this session.",
            "origin": Origin.operational,
        },
    )
    mina = create_contact(
        db,
        organization.id,
        {
            "company_id": harbor.id,
            "full_name": "Mina Patel",
            "email": "mina.patel@harbor.example",
            "phone": "+1-555-0108",
            "title": "Operations lead",
            "origin": Origin.operational,
        },
    )
    lead = create_lead(
        db,
        organization.id,
        user.id,
        {
            "title": "North pier expansion",
            "status": LeadStatus.qualified,
            "source": "Website",
            "notes": "Mina asked about bonded and cold storage at the north pier yard.",
            "company_id": harbor.id,
            "contact_id": mina.id,
            "owner_user_id": user.id,
            "origin": Origin.operational,
        },
    )
    lumen = create_company(
        db,
        organization.id,
        {
            "name": "Lumen Freight",
            "website": "https://lumen.example",
            "industry": "Freight forwarding",
            "notes": "Fictional coastal carrier in this demonstration only.",
            "origin": Origin.operational,
        },
    )
    create_contact(
        db,
        organization.id,
        {
            "company_id": lumen.id,
            "full_name": "Jonah Ellis",
            "email": "jonah.ellis@lumen.example",
            "phone": "+1-555-0148",
            "title": "Network planner",
            "origin": Origin.operational,
        },
    )
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
    db.add(
        Opportunity(
            organization_id=organization.id,
            title="North pier bonded capacity",
            value=48000,
            currency="USD",
            expected_close_date=datetime(2027, 3, 31, tzinfo=UTC),
            owner_user_id=user.id,
            company_id=harbor.id,
            contact_id=mina.id,
            lead_id=lead.id,
            stage=LeadStatus.qualified.value,
        )
    )
    db.commit()
    create_inquiry(
        db,
        organization.id,
        {
            "company_id": harbor.id,
            "lead_id": lead.id,
            "subject": "Bonded warehousing at the north pier",
            "body": "Please confirm bonded and cold storage for next quarter.",
            "origin": Origin.operational,
        },
    )
    add_interaction(
        db,
        organization.id,
        lead.id,
        user.id,
        {
            "kind": InteractionKind.note,
            "body": "Discovery note recorded for the demonstration. Nothing was sent.",
            "origin": Origin.operational,
        },
    )
    db.add(
        WorkflowTask(
            organization_id=organization.id,
            lead_id=lead.id,
            contact_id=mina.id,
            assignee_user_id=user.id,
            title="Send the bonded warehousing service sheet",
            description="Demonstration follow-up. Creating this task sends nothing.",
            due_at=datetime(2027, 3, 12, tzinfo=UTC),
            status="open",
            priority="high",
            source="manual",
        )
    )
    _inbox(db, organization, user, mina.id, lead.id)
    document_id, chunk = _knowledge(db, organization, user)
    _workflow(db, organization, user, lead.id)
    _campaign(db, organization, mina.id)
    _assistant(db, organization, user, document_id, chunk)


def _inbox(
    db: Session,
    organization: Organization,
    user: User,
    contact_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> None:
    email = InboxConversation(
        organization_id=organization.id,
        contact_id=contact_id,
        lead_id=lead_id,
        subject="Cold storage for the north pier",
        channel="email",
        status=InboxStatus.open,
        assigned_to=user.id,
        unread_count=1,
    )
    db.add(email)
    db.flush()
    db.add(
        InboxMessage(
            organization_id=organization.id,
            conversation_id=email.id,
            sender="mina.patel@harbor.example",
            recipient="inbox@harbor.example",
            body="Could you confirm bonded and cold storage at the north pier yard?",
            direction="inbound",
            channel="email",
            delivery_status="received",
            provider_message_id=f"visitor-{organization.id}-email-1",
        )
    )
    db.add(
        InboxMessage(
            organization_id=organization.id,
            conversation_id=email.id,
            sender="draft",
            recipient="mina.patel@harbor.example",
            body="Draft reply for review. This demonstration message was not sent.",
            direction="outbound",
            channel="email",
            delivery_status="draft",
            provider_message_id=f"visitor-{organization.id}-email-draft",
        )
    )
    chat = InboxConversation(
        organization_id=organization.id,
        contact_id=contact_id,
        lead_id=lead_id,
        subject="Website chat: bonded yard visit",
        channel="webchat",
        status=InboxStatus.open,
        assigned_to=user.id,
        unread_count=1,
    )
    db.add(chat)
    db.flush()
    db.add(
        InboxMessage(
            organization_id=organization.id,
            conversation_id=chat.id,
            sender="visitor",
            recipient="harbor",
            body="I would like to visit the bonded yard next quarter.",
            direction="inbound",
            channel="webchat",
            delivery_status="received",
            provider_message_id=f"visitor-{organization.id}-webchat-1",
        )
    )
    db.commit()


def _knowledge(db: Session, organization: Organization, user: User) -> tuple[uuid.UUID, Chunk]:
    payload = KNOWLEDGE_TEXT.encode()
    document = Document(
        organization_id=organization.id,
        uploaded_by=user.id,
        title=KNOWLEDGE_TITLE,
        filename="bonded-warehousing-overview.txt",
        media_type="text/plain",
        byte_size=len(payload),
        storage_path="",
        status=DocumentStatus.ready,
        origin=Origin.operational,
        content_sha256=hashlib.sha256(payload).hexdigest(),
    )
    db.add(document)
    db.flush()
    root = Path(get_settings().upload_storage_dir).expanduser().resolve()
    path = (root / str(organization.id) / str(document.id)).resolve()
    if not path.is_relative_to(root):
        raise AppError(500, "demo_limited", "The demonstration document path is invalid.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    document.storage_path = str(path)
    settings = get_settings()
    chunk = Chunk(
        organization_id=organization.id,
        document_id=document.id,
        chunk_index=0,
        page_number=1,
        content=KNOWLEDGE_TEXT,
    )
    store_chunk_embedding(
        chunk,
        hash_embedding(KNOWLEDGE_TEXT, settings.embedding_dimensions),
        settings,
    )
    db.add(chunk)
    db.flush()
    db.execute(
        update(Chunk)
        .where(Chunk.id == chunk.id)
        .values(search_vector=func.to_tsvector("english", Chunk.content))
    )
    db.commit()
    return document.id, chunk


def _workflow(db: Session, organization: Organization, user: User, lead_id: uuid.UUID) -> None:
    definition = WorkflowDefinition(
        organization_id=organization.id,
        slug="qualified-lead-follow-up",
        name="Qualified lead follow-up",
        description="Demonstration definition. It starts inactive and does not send messages.",
        version=1,
        active=False,
        definition={
            "trigger": "lead_created",
            "condition_mode": "all",
            "conditions": [{"field": "lead_status", "operator": "equals", "value": "qualified"}],
            "actions": [
                {"type": "require_approval"},
                {"type": "create_task", "title": "Send the service sheet"},
            ],
            "otherwise_actions": [],
        },
        created_by=user.id,
    )
    db.add(definition)
    db.flush()
    db.add(
        WorkflowRun(
            organization_id=organization.id,
            kind=WorkflowKind.follow_up,
            status=WorkflowStatus.completed,
            idempotency_key=hashlib.sha256(
                b"atlas-visitor-workflow:" + organization.id.bytes
            ).hexdigest(),
            lead_id=lead_id,
            origin=Origin.operational,
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


def _campaign(db: Session, organization: Organization, contact_id: uuid.UUID) -> None:
    segment = CustomerSegment(
        organization_id=organization.id,
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
    db.flush()
    db.add(
        MarketingConsent(
            organization_id=organization.id,
            contact_id=contact_id,
            status="granted",
            source="demo-session",
            consented_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
    )
    db.add(
        Campaign(
            organization_id=organization.id,
            segment_id=segment.id,
            name="Q3 cold-storage briefing",
            description="Draft only. A demonstration session cannot schedule delivery.",
            channel="email",
            status="draft",
            subject="Cold storage availability",
            body="This draft is stored for review. It has not been scheduled.",
            delivery_mode="sandbox",
        )
    )
    db.commit()


def _assistant(
    db: Session,
    organization: Organization,
    user: User,
    document_id: uuid.UUID,
    chunk: Chunk,
) -> None:
    conversation = Conversation(
        organization_id=organization.id,
        user_id=user.id,
        title="Bonded yard capacity",
    )
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            organization_id=organization.id,
            role=MessageRole.user,
            content="Is bonded warehousing available at the north pier?",
        )
    )
    answer = Message(
        conversation_id=conversation.id,
        organization_id=organization.id,
        role=MessageRole.assistant,
        content="Bonded warehousing is available at the north pier yard.",
    )
    db.add(answer)
    db.flush()
    db.add(
        MessageSource(
            message_id=answer.id,
            organization_id=organization.id,
            kind=SourceKind.document,
            document_id=document_id,
            chunk_id=chunk.id,
            page_number=1,
            title=KNOWLEDGE_TITLE,
            excerpt="Bonded warehousing is available at the north pier yard.",
        )
    )
    db.commit()
