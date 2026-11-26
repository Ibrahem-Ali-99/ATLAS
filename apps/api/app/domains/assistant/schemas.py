import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ProposalSubmit(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class SourceOut(BaseModel):
    kind: Literal["document", "crm"]
    title: str
    excerpt: str
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    page_number: int | None = None
    record_type: str | None = None
    record_id: uuid.UUID | None = None


class ProposalOut(BaseModel):
    id: uuid.UUID
    kind: Literal["follow_up", "appointment", "task"]
    status: Literal["proposed", "submitted", "dismissed"]
    title: str
    summary: str
    result_label: str
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    inquiry_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    approval_status: str | None = None
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None


class AssistantStepOut(BaseModel):
    tool_name: str
    status: Literal["succeeded", "failed", "recovered"]
    duration_ms: int
    detail: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    sources: list[SourceOut] = []
    proposals: list[ProposalOut] = []
    steps: list[AssistantStepOut] = []


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ReplyOut(BaseModel):
    conversation_id: uuid.UUID
    message: MessageOut
    document_search: Literal["ready", "empty", "unconfigured", "unavailable", "skipped"]


class ExecutionStepOut(BaseModel):
    sequence: int
    tool_name: str
    status: Literal["succeeded", "failed", "recovered"]
    duration_ms: int
    arguments: dict[str, object]
    records: list[dict[str, object]]
    error_message: str | None = None
    recovery: str | None = None


class ExecutionOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    request: str
    status: Literal["running", "completed", "failed"]
    tools: list[str]
    tokens_in: int | None
    tokens_out: int | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[ExecutionStepOut] = []


class ExecutionPage(BaseModel):
    items: list[ExecutionOut]
    page: int
    page_size: int
    total: int
