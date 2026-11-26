import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.errors import AppError
from app.domains.assistant import service as assistant_service
from app.domains.audit.models import AuditEvent
from app.domains.audit.service import record_event
from app.domains.automation.models import WorkflowKind, WorkflowRun, WorkflowStatus
from app.domains.billing.service import meter_assistant_request
from app.domains.crm.models import Company, Contact, Inquiry, Lead
from app.domains.identity.dependencies import Admin, CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.knowledge.models import Document, DocumentStatus
from app.domains.onboarding.models import AgentConfiguration, OrganizationSetup
from app.domains.provenance.origin import Origin
from app.integrations.language import get_chat_client, get_embedding_client

router = APIRouter(prefix="/organizations/{organization_id}", tags=["onboarding"])


class AgentBody(BaseModel):
    assistant_name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    tone: str = Field(min_length=1, max_length=80)
    response_language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    business_instructions: str = Field(default="", max_length=4000)


class SetupBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business_description: str | None = Field(default=None, max_length=1000)
    industry: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="UTC", max_length=80)
    language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    completed: bool = False
    agent: AgentBody | None = None


class AssistantTestBody(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@router.get("/onboarding/progress")
def onboarding_progress(member: Member, db: DbSession) -> dict[str, bool]:
    organization_id = member.organization.id
    active_crm = {
        name: select(model.id).where(
            model.organization_id == organization_id,
            model.origin == Origin.operational,
            model.archived_at.is_(None),
        )
        for name, model in (
            ("company", Company),
            ("contact", Contact),
            ("lead", Lead),
            ("inquiry", Inquiry),
        )
    }
    checks = {
        "profile": select(OrganizationSetup.organization_id).where(
            OrganizationSetup.organization_id == organization_id,
            OrganizationSetup.completed.is_(True),
        ),
        **active_crm,
        "knowledge": select(Document.id).where(
            Document.organization_id == organization_id,
            Document.origin == Origin.operational,
            Document.status == DocumentStatus.ready,
        ),
        "assistant": select(AuditEvent.id).where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.action == "onboarding.assistant_grounded",
        ),
        "workflow": select(WorkflowRun.id).where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.origin == Origin.operational,
            WorkflowRun.kind == WorkflowKind.follow_up,
            WorkflowRun.status == WorkflowStatus.completed,
            WorkflowRun.payload["workflow_definition_id"].astext.is_not(None),
            WorkflowRun.payload["outcome"].astext.is_distinct_from("skipped"),
        ),
    }
    result = db.execute(select(*(query.exists().label(name) for name, query in checks.items())))
    return dict(result.mappings().one())


def _setup(db: DbSession, organization_id: uuid.UUID) -> OrganizationSetup:
    db.execute(
        insert(OrganizationSetup)
        .values(organization_id=organization_id)
        .on_conflict_do_nothing(index_elements=[OrganizationSetup.organization_id])
    )
    return db.scalars(
        select(OrganizationSetup)
        .where(OrganizationSetup.organization_id == organization_id)
        .with_for_update()
    ).one()


def _agent(db: DbSession, organization_id: uuid.UUID) -> AgentConfiguration:
    db.execute(
        insert(AgentConfiguration)
        .values(organization_id=organization_id)
        .on_conflict_do_nothing(index_elements=[AgentConfiguration.organization_id])
    )
    return db.scalars(
        select(AgentConfiguration)
        .where(AgentConfiguration.organization_id == organization_id)
        .with_for_update()
    ).one()


@router.get("/onboarding")
def get_onboarding(admin: Admin, db: DbSession) -> dict[str, object]:
    setup = db.scalar(
        select(OrganizationSetup).where(OrganizationSetup.organization_id == admin.organization.id)
    )
    agent = db.scalar(
        select(AgentConfiguration).where(
            AgentConfiguration.organization_id == admin.organization.id
        )
    )
    return {
        "organization": {"id": admin.organization.id, "name": admin.organization.name},
        "setup": {
            "business_description": setup.business_description if setup else None,
            "industry": setup.industry if setup else None,
            "timezone": setup.timezone if setup else "UTC",
            "language": setup.language if setup else "en",
            "completed": setup.completed if setup else False,
        },
        "agent": {
            "assistant_name": agent.assistant_name if agent else "ATLAS Assistant",
            "purpose": agent.purpose
            if agent
            else "Help the team understand and act on customer information.",
            "tone": agent.tone if agent else "professional",
            "response_language": agent.response_language if agent else "en",
            "business_instructions": agent.business_instructions if agent else "",
        },
    }


@router.patch("/onboarding")
def update_onboarding(body: SetupBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError as exc:
        raise AppError(422, "invalid_timezone", "Choose a valid IANA timezone") from exc
    name = body.name.strip()
    if not name:
        raise AppError(422, "invalid_organization_name", "Enter an organization name")
    setup = _setup(db, admin.organization.id)
    admin.organization.name = name
    setup.business_description, setup.industry = body.business_description, body.industry
    setup.timezone, setup.language, setup.completed = body.timezone, body.language, body.completed
    record_event(
        db,
        admin.organization.id,
        "onboarding_updated",
        {"completed": body.completed},
        actor_id=admin.user.id,
    )
    if body.agent:
        _record_agent_configuration(body.agent, admin, db)
    db.commit()
    return get_onboarding(admin, db)


@router.patch("/agent-configuration")
def update_agent(body: AgentBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    agent = _record_agent_configuration(body, admin, db)
    db.commit()
    return {
        "assistant_name": agent.assistant_name,
        "purpose": agent.purpose,
        "tone": agent.tone,
        "response_language": agent.response_language,
        "business_instructions": agent.business_instructions,
    }


def _record_agent_configuration(
    body: AgentBody, admin: CsrfAdmin, db: DbSession
) -> AgentConfiguration:
    agent = _agent(db, admin.organization.id)
    for key, value in body.model_dump().items():
        setattr(agent, key, value)
    record_event(
        db,
        admin.organization.id,
        "agent_configuration_updated",
        {"fields": list(body.model_fields)},
        actor_id=admin.user.id,
    )
    return agent


@router.post("/onboarding/assistant-test")
def assistant_test(body: AssistantTestBody, member: CsrfMember, db: DbSession) -> dict[str, object]:
    from app.domains.demo.service import enforce_demo_assistant

    enforce_demo_assistant(db, member.organization)
    meter_assistant_request(db, member.organization.id)
    chat = get_chat_client(db, member.organization.id)
    embedder = get_embedding_client(db, member.organization.id)
    conversation = assistant_service.create_conversation(
        db, member.organization.id, member.user.id, "Onboarding assistant test"
    )
    turn = assistant_service.prepare_turn(
        db, member.organization.id, member.user.id, conversation.id, body.question, embedder, chat
    )
    if not turn.needs_model:
        return {"message": turn.refusal or "No response available.", "sources": []}
    reply = assistant_service.complete_turn(db, turn, chat)
    if reply.message.sources:
        record_event(
            db,
            member.organization.id,
            "onboarding.assistant_grounded",
            {"conversation_id": str(conversation.id)},
            actor_id=member.user.id,
        )
        db.commit()
    return {
        "message": reply.message.content,
        "sources": [source.model_dump(mode="json") for source in reply.message.sources],
    }
