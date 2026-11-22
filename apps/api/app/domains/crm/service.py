import enum
import re
import uuid
from typing import Any, cast

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.crm.models import Company, Contact, Inquiry, Interaction, Lead
from app.domains.identity.service import get_membership


def _text(value: object) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def page_bounds(page: int, page_size: int) -> tuple[int, int]:
    safe_page = max(page, 1)
    safe_size = min(max(page_size, 1), 100)
    return safe_page, safe_size


def _page[T](db: Session, query: Select[Any], page: int, page_size: int) -> tuple[list[T], int]:
    safe_page, safe_size = page_bounds(page, page_size)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.offset((safe_page - 1) * safe_size).limit(safe_size)).all()
    return cast(list[T], list(rows)), int(total)


def _require[T](record: T | None) -> T:
    if record is None:
        raise AppError(404, "not_found", "Resource not found")
    return record


def _company(db: Session, organization_id: uuid.UUID, company_id: uuid.UUID) -> Company:
    return _require(
        db.scalar(
            select(Company).where(
                Company.id == company_id, Company.organization_id == organization_id
            )
        )
    )


def _contact(db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    return _require(
        db.scalar(
            select(Contact).where(
                Contact.id == contact_id, Contact.organization_id == organization_id
            )
        )
    )


def _lead(db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
    return _require(
        db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == organization_id))
    )


def _owner(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if get_membership(db, user_id, organization_id) is None:
        raise AppError(422, "invalid_owner", "Owner must belong to this organization")


def _apply(record: object, values: dict[str, object]) -> None:
    for key, value in values.items():
        setattr(record, key, value)


def list_companies(
    db: Session, organization_id: uuid.UUID, *, q: str | None, page: int, page_size: int
) -> tuple[list[Company], int]:
    query = select(Company).where(Company.organization_id == organization_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            or_(Company.name.ilike(term), Company.industry.ilike(term), Company.website.ilike(term))
        )
    query = query.order_by(Company.name.asc())
    return _page(db, query, page, page_size)


def create_company(db: Session, organization_id: uuid.UUID, values: dict[str, object]) -> Company:
    company = Company(organization_id=organization_id, **values)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def get_company(db: Session, organization_id: uuid.UUID, company_id: uuid.UUID) -> Company:
    return _company(db, organization_id, company_id)


def update_company(
    db: Session, organization_id: uuid.UUID, company_id: uuid.UUID, values: dict[str, object]
) -> Company:
    company = _company(db, organization_id, company_id)
    _apply(company, values)
    db.commit()
    db.refresh(company)
    return company


def delete_company(db: Session, organization_id: uuid.UUID, company_id: uuid.UUID) -> None:
    company = _company(db, organization_id, company_id)
    linked = db.scalar(
        select(func.count()).select_from(Contact).where(Contact.company_id == company.id)
    ) or db.scalar(select(func.count()).select_from(Lead).where(Lead.company_id == company.id))
    if linked:
        raise AppError(
            409,
            "company_in_use",
            "Reassign or remove related contacts and leads before deleting this company",
        )
    db.delete(company)
    db.commit()


def list_contacts(
    db: Session,
    organization_id: uuid.UUID,
    *,
    q: str | None,
    company_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[Contact], int]:
    query = select(Contact).where(Contact.organization_id == organization_id)
    if company_id is not None:
        query = query.where(Contact.company_id == company_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            or_(Contact.full_name.ilike(term), Contact.email.ilike(term), Contact.title.ilike(term))
        )
    query = query.order_by(Contact.full_name.asc())
    return _page(db, query, page, page_size)


def create_contact(db: Session, organization_id: uuid.UUID, values: dict[str, object]) -> Contact:
    company_id = values.get("company_id")
    if isinstance(company_id, uuid.UUID):
        _company(db, organization_id, company_id)
    contact = Contact(organization_id=organization_id, **values)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def get_contact(db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    return _contact(db, organization_id, contact_id)


def update_contact(
    db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID, values: dict[str, object]
) -> Contact:
    contact = _contact(db, organization_id, contact_id)
    if "company_id" in values and isinstance(values["company_id"], uuid.UUID):
        _company(db, organization_id, values["company_id"])
    _apply(contact, values)
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, organization_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    contact = _contact(db, organization_id, contact_id)
    db.delete(contact)
    db.commit()


def list_leads(
    db: Session,
    organization_id: uuid.UUID,
    *,
    q: str | None,
    status: str | None,
    company_id: uuid.UUID | None,
    owner_user_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[Lead], int]:
    query = select(Lead).where(Lead.organization_id == organization_id)
    if status:
        query = query.where(Lead.status == status)
    if company_id is not None:
        query = query.where(Lead.company_id == company_id)
    if owner_user_id is not None:
        query = query.where(Lead.owner_user_id == owner_user_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(
            or_(Lead.title.ilike(term), Lead.source.ilike(term), Lead.notes.ilike(term))
        )
    query = query.order_by(Lead.updated_at.desc())
    return _page(db, query, page, page_size)


def create_lead(
    db: Session, organization_id: uuid.UUID, actor_user_id: uuid.UUID, values: dict[str, object]
) -> Lead:
    owner_id = values.get("owner_user_id") or actor_user_id
    if not isinstance(owner_id, uuid.UUID):
        raise AppError(422, "invalid_owner", "Owner must belong to this organization")
    _owner(db, organization_id, owner_id)
    company_id = values.get("company_id")
    contact_id = values.get("contact_id")
    if isinstance(company_id, uuid.UUID):
        _company(db, organization_id, company_id)
    if isinstance(contact_id, uuid.UUID):
        _contact(db, organization_id, contact_id)
    values["owner_user_id"] = owner_id
    lead = Lead(organization_id=organization_id, **values)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def get_lead(db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
    return _lead(db, organization_id, lead_id)


def update_lead(
    db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID, values: dict[str, object]
) -> Lead:
    lead = _lead(db, organization_id, lead_id)
    owner_id = values.get("owner_user_id")
    company_id = values.get("company_id")
    contact_id = values.get("contact_id")
    if isinstance(owner_id, uuid.UUID):
        _owner(db, organization_id, owner_id)
    if isinstance(company_id, uuid.UUID):
        _company(db, organization_id, company_id)
    if isinstance(contact_id, uuid.UUID):
        _contact(db, organization_id, contact_id)
    _apply(lead, values)
    db.commit()
    db.refresh(lead)
    return lead


def delete_lead(db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID) -> None:
    lead = _lead(db, organization_id, lead_id)
    db.delete(lead)
    db.commit()


def list_inquiries(
    db: Session,
    organization_id: uuid.UUID,
    *,
    q: str | None,
    company_id: uuid.UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[Inquiry], int]:
    query = select(Inquiry).where(Inquiry.organization_id == organization_id)
    if company_id is not None:
        query = query.where(Inquiry.company_id == company_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.where(or_(Inquiry.subject.ilike(term), Inquiry.body.ilike(term)))
    query = query.order_by(Inquiry.created_at.desc())
    return _page(db, query, page, page_size)


def create_inquiry(db: Session, organization_id: uuid.UUID, values: dict[str, object]) -> Inquiry:
    company_id = values.get("company_id")
    lead_id = values.get("lead_id")
    if isinstance(company_id, uuid.UUID):
        _company(db, organization_id, company_id)
    if isinstance(lead_id, uuid.UUID):
        _lead(db, organization_id, lead_id)
    inquiry = Inquiry(organization_id=organization_id, **values)
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return inquiry


def get_inquiry(db: Session, organization_id: uuid.UUID, inquiry_id: uuid.UUID) -> Inquiry:
    return _require(
        db.scalar(
            select(Inquiry).where(
                Inquiry.id == inquiry_id, Inquiry.organization_id == organization_id
            )
        )
    )


def update_inquiry(
    db: Session, organization_id: uuid.UUID, inquiry_id: uuid.UUID, values: dict[str, object]
) -> Inquiry:
    inquiry = get_inquiry(db, organization_id, inquiry_id)
    company_id = values.get("company_id")
    lead_id = values.get("lead_id")
    if isinstance(company_id, uuid.UUID):
        _company(db, organization_id, company_id)
    if isinstance(lead_id, uuid.UUID):
        _lead(db, organization_id, lead_id)
    _apply(inquiry, values)
    db.commit()
    db.refresh(inquiry)
    return inquiry


def delete_inquiry(db: Session, organization_id: uuid.UUID, inquiry_id: uuid.UUID) -> None:
    inquiry = get_inquiry(db, organization_id, inquiry_id)
    db.delete(inquiry)
    db.commit()


def list_interactions(
    db: Session, organization_id: uuid.UUID, lead_id: uuid.UUID
) -> list[Interaction]:
    _lead(db, organization_id, lead_id)
    return list(
        db.scalars(
            select(Interaction)
            .where(Interaction.lead_id == lead_id, Interaction.organization_id == organization_id)
            .order_by(Interaction.created_at.asc())
        ).all()
    )


def add_interaction(
    db: Session,
    organization_id: uuid.UUID,
    lead_id: uuid.UUID,
    author_user_id: uuid.UUID,
    values: dict[str, object],
) -> Interaction:
    _lead(db, organization_id, lead_id)
    interaction = Interaction(
        organization_id=organization_id,
        lead_id=lead_id,
        author_user_id=author_user_id,
        **values,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return interaction


_CRM_STOP_WORDS = {
    "what",
    "when",
    "where",
    "which",
    "about",
    "status",
    "with",
    "from",
    "that",
    "this",
    "have",
    "does",
    "your",
    "their",
    "lead",
    "leads",
    "company",
    "contact",
}


def _search_terms(query_text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'+-]{3,}", query_text)
    terms: list[str] = []
    for word in words:
        if word.lower() in _CRM_STOP_WORDS or word in terms:
            continue
        terms.append(word)
    return terms[:8]


def search_records(
    db: Session, organization_id: uuid.UUID, query_text: str, limit: int = 5
) -> list[dict[str, str]]:
    terms = _search_terms(query_text)
    if not terms:
        return []
    records: list[dict[str, str]] = []
    company_match = or_(*[Company.name.ilike(f"%{term}%") for term in terms])
    companies = db.scalars(
        select(Company)
        .where(Company.organization_id == organization_id, company_match)
        .order_by(Company.name.asc())
        .limit(limit)
    ).all()
    for company in companies:
        records.append(
            {
                "record_type": "company",
                "record_id": str(company.id),
                "title": company.name,
                "excerpt": company.industry or company.website or company.name,
            }
        )
    lead_match = or_(
        *[
            or_(
                Lead.title.ilike(f"%{term}%"),
                Lead.notes.ilike(f"%{term}%"),
                Lead.source.ilike(f"%{term}%"),
            )
            for term in terms
        ]
    )
    leads = db.scalars(
        select(Lead)
        .where(Lead.organization_id == organization_id, lead_match)
        .order_by(Lead.updated_at.desc())
        .limit(limit)
    ).all()
    for lead in leads:
        records.append(
            {
                "record_type": "lead",
                "record_id": str(lead.id),
                "title": lead.title,
                "excerpt": f"Status: {_text(lead.status)}. {lead.notes or ''}".strip(),
            }
        )
    contact_match = or_(
        *[
            or_(Contact.full_name.ilike(f"%{term}%"), Contact.email.ilike(f"%{term}%"))
            for term in terms
        ]
    )
    contacts = db.scalars(
        select(Contact)
        .where(Contact.organization_id == organization_id, contact_match)
        .order_by(Contact.full_name.asc())
        .limit(limit)
    ).all()
    for contact in contacts:
        records.append(
            {
                "record_type": "contact",
                "record_id": str(contact.id),
                "title": contact.full_name,
                "excerpt": contact.email or contact.title or contact.full_name,
            }
        )
    return records[:limit]
