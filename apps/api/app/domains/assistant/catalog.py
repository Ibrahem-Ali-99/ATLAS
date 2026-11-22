"""Organization-scoped reads for assistant inventory. No writes and no model."""

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.crm.models import Company, Contact, Inquiry, Lead, LeadStatus
from app.domains.knowledge.models import Document, DocumentStatus

CATALOG_LIMIT = 8
ATTENTION_STATUSES = (LeadStatus.new, LeadStatus.contacted, LeadStatus.qualified)


@dataclass(frozen=True)
class InventoryDocument:
    document_id: uuid.UUID
    title: str
    excerpt: str


@dataclass(frozen=True)
class ReadAnswer:
    content: str
    crm_records: list[dict[str, str]]
    documents: list[InventoryDocument]
    searched_crm: bool
    searched_documents: bool


def answer_inventory(db: Session, organization_id: uuid.UUID) -> ReadAnswer:
    companies = _companies(db, organization_id)
    contacts = _contacts(db, organization_id)
    leads = _attention_leads(db, organization_id)
    inquiries = _inquiries(db, organization_id)
    documents = _documents(db, organization_id)
    company_count = _count(db, Company, organization_id)
    contact_count = _count(db, Contact, organization_id)
    lead_count = _count(db, Lead, organization_id)
    inquiry_count = _count(db, Inquiry, organization_id)
    document_count = _count(db, Document, organization_id)
    ready_count = _document_status_count(db, organization_id, DocumentStatus.ready)
    failed_count = _document_status_count(db, organization_id, DocumentStatus.failed)
    lines = [
        "## Information stored for this organization",
        "",
        "Showing records for your signed-in organization only. "
        "This is an inventory of stored rows, not a description of what the documents say.",
        "",
        f"- Companies: {company_count}",
        f"- Contacts: {contact_count}",
        f"- Leads: {lead_count}",
        f"- Leads that need attention: {leads[0]} (status is new, contacted, or qualified)",
        f"- Inquiries: {inquiry_count}",
        f"- Documents: {document_count} ({ready_count} ready, {failed_count} failed)",
        "",
        "### Companies",
        *_section(companies[1], "No companies are stored."),
        "",
        "### Contacts",
        *_section(contacts[1], "No contacts are stored."),
        "",
        "### Leads that need attention",
        *_section(leads[1], "No leads are new, contacted, or qualified."),
        "",
        "### Recent inquiries",
        *_section(inquiries[1], "No inquiries are stored."),
        "",
        "### Documents",
        *_section(documents[1], "No documents are stored."),
        "",
        "Ask about one company or document when you want a fact from its contents.",
    ]
    return ReadAnswer(
        content="\n".join(lines),
        crm_records=[*companies[2], *contacts[2], *leads[2], *inquiries[2]],
        documents=documents[2],
        searched_crm=True,
        searched_documents=True,
    )


def answer_companies(db: Session, organization_id: uuid.UUID) -> ReadAnswer:
    total, lines, records = _companies(db, organization_id)
    content = _headed(
        "Companies in this organization",
        f"{total} companies are stored. Showing {len(records)}.",
        lines,
        empty="No companies are stored.",
    )
    return ReadAnswer(content, records, [], True, False)


def answer_documents(db: Session, organization_id: uuid.UUID) -> ReadAnswer:
    total, lines, documents = _documents(db, organization_id)
    content = _headed(
        "Documents in this organization",
        f"{total} documents are stored. Showing {len(documents)}. "
        "Titles and statuses only. This list does not quote their contents.",
        lines,
        empty="No documents are stored.",
    )
    return ReadAnswer(content, [], documents, False, True)


def answer_inquiries(db: Session, organization_id: uuid.UUID) -> ReadAnswer:
    total, lines, records = _inquiries(db, organization_id)
    content = _headed(
        "Recent inquiries",
        f"{total} inquiries are stored. Showing {len(records)}, newest first.",
        lines,
        empty="No inquiries are stored.",
    )
    return ReadAnswer(content, records, [], True, False)


def answer_leads(db: Session, organization_id: uuid.UUID) -> ReadAnswer:
    total, lines, records = _attention_leads(db, organization_id)
    content = _headed(
        "Leads that need attention",
        "A lead needs attention when its status is new, contacted, or qualified. "
        "Won, lost, and unqualified leads are omitted. "
        f"{total} leads need attention. Showing {len(records)}, most recently updated first.",
        lines,
        empty="No leads are new, contacted, or qualified.",
    )
    return ReadAnswer(content, records, [], True, False)


def _headed(title: str, summary: str, lines: list[str], *, empty: str) -> str:
    body = lines or [empty]
    return "\n".join(
        [
            f"## {title}",
            "",
            "Showing records for your signed-in organization only.",
            "",
            summary,
            "",
            *body,
        ]
    )


def _section(lines: list[str], empty: str) -> list[str]:
    return lines or [empty]


def _companies(
    db: Session, organization_id: uuid.UUID
) -> tuple[int, list[str], list[dict[str, str]]]:
    total = _count(db, Company, organization_id)
    rows = db.scalars(
        select(Company)
        .where(Company.organization_id == organization_id)
        .order_by(Company.name.asc())
        .limit(CATALOG_LIMIT)
    ).all()
    lines: list[str] = []
    records: list[dict[str, str]] = []
    for company in rows:
        detail = _clip(company.industry or company.website or "No industry recorded", 120)
        name = _clip(company.name, 200)
        lines.append(f"- {name}: {detail}")
        records.append(
            {
                "record_type": "company",
                "record_id": str(company.id),
                "title": name,
                "excerpt": detail,
            }
        )
    return total, lines, records


def _contacts(
    db: Session, organization_id: uuid.UUID
) -> tuple[int, list[str], list[dict[str, str]]]:
    total = _count(db, Contact, organization_id)
    rows = db.scalars(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .order_by(Contact.full_name.asc())
        .limit(CATALOG_LIMIT)
    ).all()
    lines: list[str] = []
    records: list[dict[str, str]] = []
    for contact in rows:
        detail = _clip(contact.email or contact.title or "No email recorded", 160)
        name = _clip(contact.full_name, 200)
        lines.append(f"- {name}: {detail}")
        records.append(
            {
                "record_type": "contact",
                "record_id": str(contact.id),
                "title": name,
                "excerpt": detail,
            }
        )
    return total, lines, records


def _attention_leads(
    db: Session, organization_id: uuid.UUID
) -> tuple[int, list[str], list[dict[str, str]]]:
    query = select(Lead).where(
        Lead.organization_id == organization_id,
        Lead.status.in_(ATTENTION_STATUSES),
    )
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(query.order_by(Lead.updated_at.desc()).limit(CATALOG_LIMIT)).all()
    lines: list[str] = []
    records: list[dict[str, str]] = []
    for lead in rows:
        status = _enum_text(lead.status)
        notes = _clip(lead.notes or "", 180)
        title = _clip(lead.title, 200)
        detail = f"Status: {status}. {notes}".strip()
        lines.append(f"- {title}: {detail}")
        records.append(
            {
                "record_type": "lead",
                "record_id": str(lead.id),
                "title": title,
                "excerpt": detail,
            }
        )
    return total, lines, records


def _inquiries(
    db: Session, organization_id: uuid.UUID
) -> tuple[int, list[str], list[dict[str, str]]]:
    total = _count(db, Inquiry, organization_id)
    rows = db.scalars(
        select(Inquiry)
        .where(Inquiry.organization_id == organization_id)
        .order_by(Inquiry.created_at.desc())
        .limit(CATALOG_LIMIT)
    ).all()
    lines: list[str] = []
    records: list[dict[str, str]] = []
    for inquiry in rows:
        subject = _clip(inquiry.subject, 200)
        body = _clip(inquiry.body, 180)
        lines.append(f"- {subject}: {body}")
        records.append(
            {
                "record_type": "inquiry",
                "record_id": str(inquiry.id),
                "title": subject,
                "excerpt": body or subject,
            }
        )
    return total, lines, records


def _documents(
    db: Session, organization_id: uuid.UUID
) -> tuple[int, list[str], list[InventoryDocument]]:
    total = _count(db, Document, organization_id)
    rows = db.scalars(
        select(Document)
        .where(Document.organization_id == organization_id)
        .order_by(Document.created_at.desc())
        .limit(CATALOG_LIMIT)
    ).all()
    lines: list[str] = []
    documents: list[InventoryDocument] = []
    for document in rows:
        status = _enum_text(document.status)
        title = _clip(document.title, 200)
        excerpt = f"Status: {status}. Contents are not included in this list."
        lines.append(f"- {title} ({status})")
        documents.append(InventoryDocument(document.id, title, excerpt))
    return total, lines, documents


def _count(
    db: Session,
    model: type[Company] | type[Contact] | type[Lead] | type[Inquiry] | type[Document],
    organization_id: uuid.UUID,
) -> int:
    value = db.scalar(
        select(func.count()).select_from(model).where(model.organization_id == organization_id)
    )
    return int(value or 0)


def _document_status_count(db: Session, organization_id: uuid.UUID, status: DocumentStatus) -> int:
    value = db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.organization_id == organization_id, Document.status == status)
    )
    return int(value or 0)


def _clip(value: str | None, limit: int) -> str:
    text = " ".join((value or "").replace("\x00", "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _enum_text(value: object) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)
