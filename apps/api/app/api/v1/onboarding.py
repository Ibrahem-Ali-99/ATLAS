import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import AppError
from app.domains.assistant import service as assistant_service
from app.domains.audit.service import record_event
from app.domains.identity.dependencies import Admin, CsrfAdmin, CsrfMember, DbSession
from app.domains.onboarding.models import AgentConfiguration, OrganizationSetup
from app.integrations.language import get_chat_client, get_embedding_client

router = APIRouter(prefix="/organizations/{organization_id}", tags=["onboarding"])


class SetupBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business_description: str | None = Field(default=None, max_length=1000)
    industry: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="UTC", max_length=80)
    language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    completed: bool = False


class AgentBody(BaseModel):
    assistant_name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    tone: str = Field(min_length=1, max_length=80)
    response_language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    business_instructions: str = Field(default="", max_length=4000)


class AssistantTestBody(BaseModel):
    question: str = Field(min_length=2, max_length=500)


def _setup(db: DbSession, organization_id: uuid.UUID) -> OrganizationSetup:
    row = db.scalar(
        select(OrganizationSetup).where(OrganizationSetup.organization_id == organization_id)
    )
    if row is None:
        row = OrganizationSetup(organization_id=organization_id)
        db.add(row)
        db.flush()
    return row


def _agent(db: DbSession, organization_id: uuid.UUID) -> AgentConfiguration:
    row = db.scalar(
        select(AgentConfiguration).where(AgentConfiguration.organization_id == organization_id)
    )
    if row is None:
        row = AgentConfiguration(organization_id=organization_id)
        db.add(row)
        db.flush()
    return row


@router.get("/onboarding")
def get_onboarding(admin: Admin, db: DbSession) -> dict[str, object]:
    setup = _setup(db, admin.organization.id)
    agent = _agent(db, admin.organization.id)
    db.commit()
    return {
        "organization": {"id": admin.organization.id, "name": admin.organization.name},
        "setup": {
            "business_description": setup.business_description,
            "industry": setup.industry,
            "timezone": setup.timezone,
            "language": setup.language,
            "completed": setup.completed,
        },
        "agent": {
            "assistant_name": agent.assistant_name,
            "purpose": agent.purpose,
            "tone": agent.tone,
            "response_language": agent.response_language,
            "business_instructions": agent.business_instructions,
        },
    }


@router.patch("/onboarding")
def update_onboarding(body: SetupBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError as exc:
        raise AppError(422, "invalid_timezone", "Choose a valid IANA timezone") from exc
    setup = _setup(db, admin.organization.id)
    admin.organization.name = body.name.strip()
    setup.business_description, setup.industry = body.business_description, body.industry
    setup.timezone, setup.language, setup.completed = body.timezone, body.language, body.completed
    record_event(
        db,
        admin.organization.id,
        "onboarding_updated",
        {"completed": body.completed},
        actor_id=admin.user.id,
    )
    db.commit()
    return get_onboarding(admin, db)


@router.patch("/agent-configuration")
def update_agent(body: AgentBody, admin: CsrfAdmin, db: DbSession) -> dict[str, object]:
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
    db.commit()
    return {
        "assistant_name": agent.assistant_name,
        "purpose": agent.purpose,
        "tone": agent.tone,
        "response_language": agent.response_language,
        "business_instructions": agent.business_instructions,
    }


@router.post("/onboarding/assistant-test")
def assistant_test(body: AssistantTestBody, member: CsrfMember, db: DbSession) -> dict[str, object]:
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
    return {
        "message": reply.message.content,
        "sources": [source.model_dump(mode="json") for source in reply.message.sources],
    }
