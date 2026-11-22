import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.crm.models import InteractionKind, LeadStatus
from app.domains.provenance.origin import Origin


class Page(BaseModel):
    page: int
    page_size: int
    total: int


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    industry: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    origin: Origin | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    industry: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    website: str | None
    industry: str | None
    notes: str | None
    origin: Origin
    created_at: datetime
    updated_at: datetime


class CompanyPage(Page):
    items: list[CompanyOut]


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=120)
    company_id: uuid.UUID | None = None
    origin: Origin | None = None


class ContactUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=120)
    company_id: uuid.UUID | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    company_id: uuid.UUID | None
    full_name: str
    email: str | None
    phone: str | None
    title: str | None
    origin: Origin
    created_at: datetime
    updated_at: datetime


class ContactPage(Page):
    items: list[ContactOut]


class LeadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    status: LeadStatus = LeadStatus.new
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    origin: Origin | None = None


class LeadUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: LeadStatus | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    owner_user_id: uuid.UUID
    title: str
    status: LeadStatus
    source: str | None
    notes: str | None
    origin: Origin
    created_at: datetime
    updated_at: datetime


class LeadPage(Page):
    items: list[LeadOut]


class InquiryCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    company_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    origin: Origin | None = None


class InquiryUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    company_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None


class InquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    company_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    origin: Origin
    subject: str
    body: str
    created_at: datetime


class InquiryPage(Page):
    items: list[InquiryOut]


class InteractionCreate(BaseModel):
    kind: InteractionKind = InteractionKind.note
    body: str = Field(min_length=1, max_length=4000)


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    lead_id: uuid.UUID
    author_user_id: uuid.UUID
    kind: InteractionKind
    body: str
    created_at: datetime
