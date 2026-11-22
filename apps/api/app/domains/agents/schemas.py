import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domains.agents.models import RunStatus
from app.domains.approvals.schemas import ApprovalOut


class StartRun(BaseModel):
    inquiry_id: uuid.UUID


class AgentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    step: str
    status: str
    detail: dict[str, Any]
    error_message: str | None
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    inquiry_id: uuid.UUID
    inquiry_subject: str = ""
    started_by: uuid.UUID
    status: RunStatus
    qualification: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class AgentRunPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[AgentRunOut]


class AgentRunDetail(BaseModel):
    run: AgentRunOut
    events: list[AgentEventOut]
    approvals: list[ApprovalOut]
