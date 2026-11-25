import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.crm.schemas import Page
from app.domains.knowledge.models import DocumentStatus
from app.domains.provenance.origin import Origin


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    uploaded_by: uuid.UUID
    title: str
    filename: str
    media_type: str
    byte_size: int
    status: DocumentStatus
    origin: Origin
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentPage(Page):
    items: list[DocumentOut]


class ChunkOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    page_number: int | None
    content: str
    score: float


class ChunkPage(BaseModel):
    items: list[ChunkOut]


class EvaluationQuestionCreate(BaseModel):
    question: str
    scenario: str = Field(
        default="grounded",
        pattern="^(grounded|missing_knowledge|unsupported_claim|human_handoff|low_confidence|memory|tenant_isolation)$",
    )
    expected_behavior: str = Field(default="answer", pattern="^(answer|fallback|handoff)$")
    expected_evidence: list[str] = Field(default_factory=list)
    expected_answer: str | None = None


class EvaluationQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    question: str
    scenario: str
    expected_behavior: str
    expected_evidence: list[str]
    expected_answer: str | None
    created_at: datetime


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    question_id: uuid.UUID
    model_identifier: str
    configuration_version: str
    retrieved_sources: list[dict[str, object]]
    evidence_match: bool
    answer_grounded: bool | None
    failure_reason: str | None
    case_result: dict[str, object]
    created_at: datetime
