import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
