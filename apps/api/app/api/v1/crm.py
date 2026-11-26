import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.errors import AppError
from app.domains.crm import profile, service
from app.domains.crm.models import Company, Contact, Lead, LeadStatus, Opportunity, PipelineStage
from app.domains.crm.schemas import (
    CompanyCreate,
    CompanyOut,
    CompanyPage,
    CompanyUpdate,
    ContactCreate,
    ContactOut,
    ContactPage,
    ContactUpdate,
    InquiryCreate,
    InquiryOut,
    InquiryPage,
    InquiryUpdate,
    InteractionCreate,
    InteractionOut,
    LeadCreate,
    LeadOut,
    LeadPage,
    LeadUpdate,
)
from app.domains.identity.dependencies import CsrfAdmin, CsrfMember, DbSession, Member
from app.domains.identity.models import Membership, User
from app.domains.provenance.origin import Origin

router = APIRouter(prefix="/organizations/{organization_id}", tags=["crm"])


class StageBody(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    position: int = Field(ge=0, le=100)
    probability: float | None = Field(default=None, ge=0, le=1)


class StageOrderBody(BaseModel):
    keys: list[str] = Field(min_length=1)


class OpportunityBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    value: float | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    expected_close_date: str | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    stage: str = "new"
    owner_user_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    loss_reason: str | None = Field(default=None, max_length=240)


class OpportunityUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    stage: str | None = None
    value: float | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    expected_close_date: str | None = None
    owner_user_id: uuid.UUID | None = None
    loss_reason: str | None = Field(default=None, max_length=240)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None


def _page(page: int, page_size: int, total: int) -> dict[str, int]:
    safe_page, safe_size = service.page_bounds(page, page_size)
    return {"page": safe_page, "page_size": safe_size, "total": total}


@router.get("/pipeline/stages")
def list_pipeline_stages(member: Member, db: DbSession) -> list[dict[str, object]]:
    rows = list(
        db.scalars(
            select(PipelineStage)
            .where(PipelineStage.organization_id == member.organization.id)
            .order_by(PipelineStage.position)
        )
    )
    if not rows:
        rows = [
            PipelineStage(
                key=item.value, label=item.value.replace("_", " ").title(), position=index
            )
            for index, item in enumerate(LeadStatus)
        ]
    return [
        {
            "key": row.key,
            "label": row.label,
            "position": row.position,
            "probability": row.probability,
            "active": row.active,
        }
        for row in rows
    ]


@router.post("/pipeline/stages", status_code=201)
def create_pipeline_stage(body: StageBody, member: CsrfMember, db: DbSession) -> dict[str, object]:
    key = "-".join(body.label.lower().split())[:40]
    row = PipelineStage(
        organization_id=member.organization.id,
        key=key,
        label=body.label,
        position=body.position,
        probability=body.probability,
    )
    db.add(row)
    db.commit()
    return {"key": row.key, "label": row.label, "position": row.position, "active": row.active}


@router.patch("/pipeline/stages/{stage_key}")
def update_pipeline_stage(
    stage_key: str, body: StageBody, member: CsrfAdmin, db: DbSession
) -> dict[str, object]:
    row = db.scalar(
        select(PipelineStage).where(
            PipelineStage.organization_id == member.organization.id,
            PipelineStage.key == stage_key,
        )
    )
    if row is None:
        raise AppError(404, "stage_not_found", "Pipeline stage not found")
    row.label = body.label
    row.position = body.position
    row.probability = body.probability
    db.commit()
    return {
        "key": row.key,
        "label": row.label,
        "position": row.position,
        "probability": row.probability,
        "active": row.active,
    }


@router.post("/pipeline/stages/reorder")
def reorder_pipeline_stages(
    body: StageOrderBody, member: CsrfAdmin, db: DbSession
) -> list[dict[str, object]]:
    rows = list(
        db.scalars(
            select(PipelineStage).where(PipelineStage.organization_id == member.organization.id)
        )
    )
    by_key = {row.key: row for row in rows}
    if set(body.keys) != set(by_key) or len(body.keys) != len(by_key):
        raise AppError(
            422, "invalid_stage_order", "Stage order must include each organization stage once"
        )
    for index, row in enumerate(sorted(rows, key=lambda item: item.position)):
        row.position = 10000 + index
    db.flush()
    for index, key in enumerate(body.keys):
        by_key[key].position = index
    db.commit()
    return [
        {
            "key": row.key,
            "label": row.label,
            "position": row.position,
            "probability": row.probability,
            "active": row.active,
        }
        for row in sorted(rows, key=lambda item: item.position)
    ]


@router.get("/opportunities")
def list_opportunities(member: Member, db: DbSession) -> list[dict[str, object]]:
    rows = db.scalars(
        select(Opportunity)
        .where(
            Opportunity.organization_id == member.organization.id, Opportunity.archived_at.is_(None)
        )
        .order_by(Opportunity.updated_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "value": row.value,
            "currency": row.currency,
            "stage": row.stage,
            "probability": row.probability,
            "owner_user_id": row.owner_user_id,
            "company_id": row.company_id,
            "contact_id": row.contact_id,
            "lead_id": row.lead_id,
            "expected_close_date": row.expected_close_date,
            "loss_reason": row.loss_reason,
        }
        for row in rows
    ]


@router.post("/opportunities", status_code=201)
def create_opportunity(
    body: OpportunityBody, member: CsrfMember, db: DbSession
) -> dict[str, object]:
    owner = body.owner_user_id or member.user.id
    for model, value in (
        (Company, body.company_id),
        (Contact, body.contact_id),
        (Lead, body.lead_id),
    ):
        if (
            value is not None
            and db.scalar(
                select(model).where(
                    model.id == value, model.organization_id == member.organization.id
                )
            )
            is None
        ):
            raise AppError(404, "related_record_not_found", "Related record not found")
    values = body.model_dump(exclude={"owner_user_id", "expected_close_date"})
    values["expected_close_date"] = (
        datetime.fromisoformat(body.expected_close_date) if body.expected_close_date else None
    )
    row = Opportunity(organization_id=member.organization.id, owner_user_id=owner, **values)
    db.add(row)
    db.commit()
    return {"id": row.id, "title": row.title, "stage": row.stage}


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: uuid.UUID,
    body: OpportunityUpdateBody,
    member: CsrfMember,
    db: DbSession,
) -> dict[str, object]:
    row = db.scalar(
        select(Opportunity)
        .where(
            Opportunity.id == opportunity_id,
            Opportunity.organization_id == member.organization.id,
            Opportunity.archived_at.is_(None),
        )
        .with_for_update()
    )
    if row is None:
        raise AppError(404, "opportunity_not_found", "Opportunity not found")
    values = body.model_dump(exclude_unset=True)
    if (
        body.owner_user_id is not None
        and db.scalar(
            select(Membership)
            .join(Membership.user)
            .where(
                Membership.organization_id == member.organization.id,
                Membership.user_id == body.owner_user_id,
                User.is_active.is_(True),
            )
        )
        is None
    ):
        raise AppError(404, "owner_not_found", "Owner is not an active organization member")
    for model, key in ((Company, "company_id"), (Contact, "contact_id"), (Lead, "lead_id")):
        value = values.get(key)
        if (
            value is not None
            and db.scalar(
                select(model).where(
                    model.id == value, model.organization_id == member.organization.id
                )
            )
            is None
        ):
            raise AppError(404, "related_record_not_found", "Related record not found")
    if (
        body.stage is not None
        and db.scalar(
            select(PipelineStage.id).where(
                PipelineStage.organization_id == member.organization.id,
                PipelineStage.key == body.stage,
                PipelineStage.active.is_(True),
            )
        )
        is None
        and body.stage not in {item.value for item in LeadStatus}
    ):
        raise AppError(422, "invalid_pipeline_stage", "Pipeline stage is not configured")
    previous_stage = row.stage
    if "expected_close_date" in values:
        values["expected_close_date"] = (
            datetime.fromisoformat(values["expected_close_date"])
            if values["expected_close_date"]
            else None
        )
    for key, value in values.items():
        setattr(row, key, value)
    if body.stage is not None and body.stage != previous_stage:
        from app.domains.automation.workflows import dispatch_pending, stage_opportunity_changed

        stage_opportunity_changed(db, member.organization.id, row.id, previous_stage, row.stage)
        db.commit()
        dispatch_pending(db, member.organization.id)
    else:
        db.commit()
    return {"id": row.id, "title": row.title, "stage": row.stage, "loss_reason": row.loss_reason}


@router.delete("/pipeline/stages/{stage_key}", status_code=204)
def delete_pipeline_stage(stage_key: str, member: CsrfAdmin, db: DbSession) -> Response:
    row = db.scalar(
        select(PipelineStage).where(
            PipelineStage.organization_id == member.organization.id,
            PipelineStage.key == stage_key,
        )
    )
    if row is None:
        raise AppError(404, "stage_not_found", "Pipeline stage not found")
    if (
        db.scalar(
            select(Opportunity.id).where(
                Opportunity.organization_id == member.organization.id,
                Opportunity.stage == stage_key,
                Opportunity.archived_at.is_(None),
            )
        )
        is not None
    ):
        raise AppError(409, "stage_in_use", "Move opportunities before deleting this stage")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/companies", response_model=CompanyPage)
def list_companies(
    member: Member,
    db: DbSession,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = False,
    sort: Literal["name", "updated"] = "name",
) -> CompanyPage:
    items, total = service.list_companies(
        db,
        member.organization.id,
        q=q,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
        sort=sort,
    )
    return CompanyPage(
        items=[CompanyOut.model_validate(item) for item in items], **_page(page, page_size, total)
    )


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyCreate, member: CsrfMember, db: DbSession) -> CompanyOut:
    company = service.create_company(db, member.organization.id, body.model_dump())
    return CompanyOut.model_validate(company)


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: uuid.UUID, member: Member, db: DbSession) -> CompanyOut:
    return CompanyOut.model_validate(service.get_company(db, member.organization.id, company_id))


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID, body: CompanyUpdate, member: CsrfMember, db: DbSession
) -> CompanyOut:
    company = service.update_company(
        db, member.organization.id, company_id, body.model_dump(exclude_unset=True)
    )
    return CompanyOut.model_validate(company)


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_company(db, member.organization.id, company_id)
    return Response(status_code=204)


@router.post("/companies/{company_id}/restore", response_model=CompanyOut)
def restore_company(company_id: uuid.UUID, member: CsrfMember, db: DbSession) -> CompanyOut:
    return CompanyOut.model_validate(
        service.restore_company(db, member.organization.id, company_id)
    )


@router.get("/contacts", response_model=ContactPage)
def list_contacts(
    member: Member,
    db: DbSession,
    q: str | None = None,
    company_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = False,
    sort: Literal["name", "updated"] = "name",
) -> ContactPage:
    items, total = service.list_contacts(
        db,
        member.organization.id,
        q=q,
        company_id=company_id,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
        sort=sort,
    )
    return ContactPage(
        items=[ContactOut.model_validate(item) for item in items], **_page(page, page_size, total)
    )


@router.post("/contacts", response_model=ContactOut, status_code=201)
def create_contact(body: ContactCreate, member: CsrfMember, db: DbSession) -> ContactOut:
    contact = service.create_contact(db, member.organization.id, body.model_dump())
    return ContactOut.model_validate(contact)


@router.get("/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: uuid.UUID, member: Member, db: DbSession) -> ContactOut:
    return ContactOut.model_validate(service.get_contact(db, member.organization.id, contact_id))


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID, body: ContactUpdate, member: CsrfMember, db: DbSession
) -> ContactOut:
    contact = service.update_contact(
        db, member.organization.id, contact_id, body.model_dump(exclude_unset=True)
    )
    return ContactOut.model_validate(contact)


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_contact(db, member.organization.id, contact_id)
    return Response(status_code=204)


@router.post("/contacts/{contact_id}/restore", response_model=ContactOut)
def restore_contact(contact_id: uuid.UUID, member: CsrfMember, db: DbSession) -> ContactOut:
    return ContactOut.model_validate(
        service.restore_contact(db, member.organization.id, contact_id)
    )


@router.get("/leads", response_model=LeadPage)
def list_leads(
    member: Member,
    db: DbSession,
    q: str | None = None,
    status: LeadStatus | None = None,
    company_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
    origin: Origin | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = False,
    sort: Literal["updated", "title"] = "updated",
) -> LeadPage:
    items, total = service.list_leads(
        db,
        member.organization.id,
        q=q,
        status=status.value if status is not None else None,
        company_id=company_id,
        owner_user_id=owner_user_id,
        origin=origin.value if origin is not None else None,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
        sort=sort,
    )
    return LeadPage(
        items=[LeadOut.model_validate(item) for item in items], **_page(page, page_size, total)
    )


@router.post("/leads", response_model=LeadOut, status_code=201)
def create_lead(body: LeadCreate, member: CsrfMember, db: DbSession) -> LeadOut:
    lead = service.create_lead(
        db, member.organization.id, member.user.id, body.model_dump(), commit=False
    )
    from app.domains.automation.workflows import dispatch_pending, stage_lead_created

    stage_lead_created(db, member.organization.id, lead.id, None)
    db.commit()
    dispatch_pending(db, member.organization.id)
    return LeadOut.model_validate(lead)


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: uuid.UUID, member: Member, db: DbSession) -> LeadOut:
    return LeadOut.model_validate(service.get_lead(db, member.organization.id, lead_id))


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: uuid.UUID, body: LeadUpdate, member: CsrfMember, db: DbSession) -> LeadOut:
    before = service.get_lead(db, member.organization.id, lead_id, lock=True)
    previous_status = before.status.value
    lead = service.update_lead(
        db, member.organization.id, lead_id, body.model_dump(exclude_unset=True), commit=False
    )
    if "status" in body.model_fields_set:
        from app.domains.automation.workflows import dispatch_pending, stage_lead_status_changed

        stage_lead_status_changed(
            db, member.organization.id, lead.id, previous_status, lead.status.value
        )
        db.commit()
        dispatch_pending(db, member.organization.id)
    else:
        db.commit()
    return LeadOut.model_validate(lead)


@router.delete("/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_lead(db, member.organization.id, lead_id)
    return Response(status_code=204)


@router.get("/customer-profile")
def get_customer_profile(
    member: Member,
    db: DbSession,
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
) -> dict[str, object]:
    return profile.customer_profile(
        db,
        member.organization.id,
        company_id=company_id,
        contact_id=contact_id,
        lead_id=lead_id,
    )


@router.post("/leads/{lead_id}/convert")
def convert_lead(lead_id: uuid.UUID, member: CsrfMember, db: DbSession) -> dict[str, object]:
    before = service.get_lead(db, member.organization.id, lead_id, lock=True)
    previous = before.status.value
    opportunity, created = service.convert_lead(db, member.organization.id, lead_id)
    if created and previous != before.status.value:
        from app.domains.automation.workflows import dispatch_pending, stage_lead_status_changed

        stage_lead_status_changed(
            db, member.organization.id, before.id, previous, before.status.value
        )
        db.commit()
        dispatch_pending(db, member.organization.id)
    else:
        db.commit()
    return {
        "id": opportunity.id,
        "title": opportunity.title,
        "stage": opportunity.stage,
        "created": created,
    }


@router.post("/leads/{lead_id}/restore", response_model=LeadOut)
def restore_lead(lead_id: uuid.UUID, member: CsrfMember, db: DbSession) -> LeadOut:
    return LeadOut.model_validate(service.restore_lead(db, member.organization.id, lead_id))


@router.get("/leads/{lead_id}/interactions", response_model=list[InteractionOut])
def list_interactions(lead_id: uuid.UUID, member: Member, db: DbSession) -> list[InteractionOut]:
    rows = service.list_interactions(db, member.organization.id, lead_id)
    return [InteractionOut.model_validate(row) for row in rows]


@router.post("/leads/{lead_id}/interactions", response_model=InteractionOut, status_code=201)
def add_interaction(
    lead_id: uuid.UUID, body: InteractionCreate, member: CsrfMember, db: DbSession
) -> InteractionOut:
    interaction = service.add_interaction(
        db, member.organization.id, lead_id, member.user.id, body.model_dump()
    )
    return InteractionOut.model_validate(interaction)


@router.get("/inquiries", response_model=InquiryPage)
def list_inquiries(
    member: Member,
    db: DbSession,
    q: str | None = None,
    company_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = False,
) -> InquiryPage:
    items, total = service.list_inquiries(
        db,
        member.organization.id,
        q=q,
        company_id=company_id,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
    )
    return InquiryPage(
        items=[InquiryOut.model_validate(item) for item in items], **_page(page, page_size, total)
    )


@router.post("/inquiries", response_model=InquiryOut, status_code=201)
def create_inquiry(body: InquiryCreate, member: CsrfMember, db: DbSession) -> InquiryOut:
    inquiry = service.create_inquiry(db, member.organization.id, body.model_dump())
    return InquiryOut.model_validate(inquiry)


@router.get("/inquiries/{inquiry_id}", response_model=InquiryOut)
def get_inquiry(inquiry_id: uuid.UUID, member: Member, db: DbSession) -> InquiryOut:
    return InquiryOut.model_validate(service.get_inquiry(db, member.organization.id, inquiry_id))


@router.patch("/inquiries/{inquiry_id}", response_model=InquiryOut)
def update_inquiry(
    inquiry_id: uuid.UUID, body: InquiryUpdate, member: CsrfMember, db: DbSession
) -> InquiryOut:
    inquiry = service.update_inquiry(
        db, member.organization.id, inquiry_id, body.model_dump(exclude_unset=True)
    )
    return InquiryOut.model_validate(inquiry)


@router.delete("/inquiries/{inquiry_id}", status_code=204)
def delete_inquiry(inquiry_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_inquiry(db, member.organization.id, inquiry_id)
    return Response(status_code=204)


@router.post("/inquiries/{inquiry_id}/restore", response_model=InquiryOut)
def restore_inquiry(inquiry_id: uuid.UUID, member: CsrfMember, db: DbSession) -> InquiryOut:
    return InquiryOut.model_validate(
        service.restore_inquiry(db, member.organization.id, inquiry_id)
    )
