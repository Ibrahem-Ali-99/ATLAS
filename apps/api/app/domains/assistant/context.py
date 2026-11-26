"""Choose CRM rows for a question.

Name matches outrank a shared incidental word. When the question names a
company, that company's leads and contacts are eligible too.
"""

import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.crm.models import Company, Contact, Lead
from app.domains.crm.service import search_records

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'+-]{3,}")
_STOP = {
    "about",
    "company",
    "contact",
    "does",
    "from",
    "have",
    "lead",
    "leads",
    "status",
    "that",
    "their",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}


def retrieve_crm_records(
    db: Session, organization_id: uuid.UUID, query_text: str, limit: int = 5
) -> list[dict[str, str]]:
    pooled = list(search_records(db, organization_id, query_text, limit=8))
    for company in _named_companies(db, organization_id, query_text):
        pooled.append(_company_row(company))
        leads = db.scalars(
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.company_id == company.id,
                Lead.archived_at.is_(None),
            )
            .order_by(Lead.updated_at.desc())
            .limit(3)
        ).all()
        pooled.extend(_lead_row(lead) for lead in leads)
        contacts = db.scalars(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.company_id == company.id,
            )
            .order_by(Contact.full_name.asc())
            .limit(3)
        ).all()
        pooled.extend(_contact_row(contact) for contact in contacts)
    ranked: dict[tuple[str, str], tuple[int, dict[str, str]]] = {}
    for record in pooled:
        key = (record["record_type"], record["record_id"])
        score = _score(query_text, record)
        current = ranked.get(key)
        if current is None or score > current[0]:
            ranked[key] = (score, record)
    ordered = sorted(ranked.values(), key=lambda item: item[0], reverse=True)
    return [record for _score_value, record in ordered[:limit]]


def _named_companies(db: Session, organization_id: uuid.UUID, query_text: str) -> list[Company]:
    terms = _terms(query_text)
    distinctive = [term for term in terms if len(term) >= 5]
    if not distinctive:
        return []
    rows = db.scalars(
        select(Company)
        .where(
            Company.organization_id == organization_id,
            Company.archived_at.is_(None),
            or_(*[Company.name.ilike(f"%{term}%") for term in distinctive[:6]]),
        )
        .order_by(Company.name.asc())
        .limit(6)
    ).all()
    lowered = query_text.lower()
    named: list[Company] = []
    for company in rows:
        name = company.name.lower()
        name_terms = _terms(company.name)
        if name in lowered or name_terms & set(distinctive):
            named.append(company)
    return named


def _terms(text: str) -> set[str]:
    found: set[str] = set()
    for word in _TOKEN.findall(text):
        lowered = word.lower()
        if lowered not in _STOP:
            found.add(lowered)
    return found


def _score(query_text: str, record: dict[str, str]) -> int:
    terms = _terms(query_text)
    haystack = f"{record['title']} {record['excerpt']}".lower()
    overlap = sum(1 for term in terms if term in haystack)
    if record["title"].lower() in query_text.lower():
        overlap += 3
    return overlap


def _company_row(company: Company) -> dict[str, str]:
    return {
        "record_type": "company",
        "record_id": str(company.id),
        "title": company.name,
        "excerpt": company.industry or company.website or company.name,
    }


def _lead_row(lead: Lead) -> dict[str, str]:
    status = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
    return {
        "record_type": "lead",
        "record_id": str(lead.id),
        "title": lead.title,
        "excerpt": f"Status: {status}. {lead.notes or ''}".strip(),
    }


def _contact_row(contact: Contact) -> dict[str, str]:
    return {
        "record_type": "contact",
        "record_id": str(contact.id),
        "title": contact.full_name,
        "excerpt": contact.email or contact.title or contact.full_name,
    }
