import uuid

from fastapi import APIRouter, Query, Response

from app.domains.crm import service
from app.domains.crm.models import LeadStatus
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
from app.domains.identity.dependencies import CsrfMember, DbSession, Member
from app.domains.provenance.origin import Origin

router = APIRouter(prefix="/organizations/{organization_id}", tags=["crm"])


def _page(page: int, page_size: int, total: int) -> dict[str, int]:
    safe_page, safe_size = service.page_bounds(page, page_size)
    return {"page": safe_page, "page_size": safe_size, "total": total}


@router.get("/companies", response_model=CompanyPage)
def list_companies(
    member: Member,
    db: DbSession,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_archived: bool = False,
) -> CompanyPage:
    items, total = service.list_companies(
        db,
        member.organization.id,
        q=q,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
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
) -> ContactPage:
    items, total = service.list_contacts(
        db,
        member.organization.id,
        q=q,
        company_id=company_id,
        page=page,
        page_size=page_size,
        include_archived=include_archived,
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
    )
    return LeadPage(
        items=[LeadOut.model_validate(item) for item in items], **_page(page, page_size, total)
    )


@router.post("/leads", response_model=LeadOut, status_code=201)
def create_lead(body: LeadCreate, member: CsrfMember, db: DbSession) -> LeadOut:
    lead = service.create_lead(db, member.organization.id, member.user.id, body.model_dump())
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
    lead = service.update_lead(
        db, member.organization.id, lead_id, body.model_dump(exclude_unset=True)
    )
    return LeadOut.model_validate(lead)


@router.delete("/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: uuid.UUID, member: CsrfMember, db: DbSession) -> Response:
    service.delete_lead(db, member.organization.id, lead_id)
    return Response(status_code=204)


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
