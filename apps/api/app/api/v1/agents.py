import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.domains.agents import service
from app.domains.agents.models import RunStatus
from app.domains.agents.schemas import (
    AgentEventOut,
    AgentRunDetail,
    AgentRunOut,
    AgentRunPage,
    StartRun,
)
from app.domains.approvals.schemas import ApprovalOut
from app.domains.crm import service as crm
from app.domains.identity.dependencies import CsrfMember, DbSession, Member
from app.domains.provenance.origin import DataScope
from app.integrations.language import ChatClient, get_chat_client

router = APIRouter(prefix="/organizations/{organization_id}", tags=["agents"])
ChatDep = Annotated[ChatClient, Depends(get_chat_client)]


def _run_out(run: object, subject: str) -> AgentRunOut:
    model = AgentRunOut.model_validate(run)
    return model.model_copy(update={"inquiry_subject": subject})


def _detail(
    db: DbSession, organization_id: uuid.UUID, run_id: uuid.UUID, subject: str
) -> AgentRunDetail:
    run = service.get_run(db, organization_id, run_id)
    events = service.run_events(db, organization_id, run_id)
    approvals = service.run_approvals(db, organization_id, run_id)
    return AgentRunDetail(
        run=_run_out(run, subject),
        events=[AgentEventOut.model_validate(item) for item in events],
        approvals=[ApprovalOut.model_validate(item) for item in approvals],
    )


@router.get("/agent-runs", response_model=AgentRunPage)
def list_runs(
    member: Member,
    db: DbSession,
    status: RunStatus | None = None,
    scope: DataScope = DataScope.operational,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AgentRunPage:
    rows, total = service.list_runs(
        db,
        member.organization.id,
        status=status,
        page=page,
        page_size=page_size,
        scope=scope,
    )
    return AgentRunPage(
        page=page,
        page_size=page_size,
        total=total,
        items=[_run_out(run, subject) for run, subject in rows],
    )


@router.post("/agent-runs", response_model=AgentRunDetail, status_code=201)
def start_run(body: StartRun, member: CsrfMember, db: DbSession, chat: ChatDep) -> AgentRunDetail:
    run = service.start_run(db, member.organization.id, member.user.id, body.inquiry_id, chat)
    inquiry = crm.get_inquiry(db, member.organization.id, run.inquiry_id)
    return _detail(db, member.organization.id, run.id, inquiry.subject)


@router.get("/agent-runs/{run_id}", response_model=AgentRunDetail)
def get_run(run_id: uuid.UUID, member: Member, db: DbSession) -> AgentRunDetail:
    run = service.get_run(db, member.organization.id, run_id)
    inquiry = crm.get_inquiry(db, member.organization.id, run.inquiry_id)
    return _detail(db, member.organization.id, run.id, inquiry.subject)


@router.post("/agent-runs/{run_id}/resume", response_model=AgentRunDetail)
def resume_run(
    run_id: uuid.UUID, member: CsrfMember, db: DbSession, chat: ChatDep
) -> AgentRunDetail:
    run = service.resume_run(db, member.organization.id, run_id, chat)
    inquiry = crm.get_inquiry(db, member.organization.id, run.inquiry_id)
    return _detail(db, member.organization.id, run.id, inquiry.subject)
