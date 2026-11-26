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


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    sources: list[SourceOut] = []
    proposals: list[ProposalOut] = []


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
