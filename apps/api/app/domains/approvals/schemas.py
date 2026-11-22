import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domains.approvals.models import ActionType, ApprovalStatus


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    run_id: uuid.UUID
    requested_by: uuid.UUID
    action_type: ActionType
    position: int
    payload: dict[str, Any]
    payload_hash: str
    status: ApprovalStatus
    expires_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    executed_at: datetime | None
    execution_result: dict[str, Any] | None
    execution_error: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ApprovalOut]
