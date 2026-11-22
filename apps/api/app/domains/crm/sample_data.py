"""Clearly synthetic CRM rows for the local seed. Not production data."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.crm.models import (
    Company,
    Contact,
    Inquiry,
    Interaction,
    InteractionKind,
    Lead,
    LeadStatus,
)
from app.domains.identity.models import Organization, User
from app.domains.provenance.origin import Origin


def seed_sample_crm(
    db: Session,
    *,
    atlas: Organization,
    northwind: Organization,
    admin: User,
    outsider: User,
) -> None:
    harbor = _company(
        db,
        atlas,
        name="Harbor & Co.",
        website="https://harbor.example",
        industry="Logistics",
        notes="Synthetic demonstration company.",
    )
    contact = _contact(
        db,
        atlas,
        harbor,
        full_name="Mina Patel",
        email="mina.patel@harbor.example",
        title="Operations Lead",
    )
    lead = _lead(
        db,
        atlas,
        harbor,
        contact,
        admin,
        title="North pier expansion",
        status=LeadStatus.qualified,
        source="Website inquiry",
        notes="Synthetic lead asking about warehousing capacity.",
    )
    _interaction(
        db,
        atlas,
        lead,
        admin,
        "Asked for a written overview of warehousing services.",
    )
    _inquiry(
        db,
        atlas,
        harbor,
        lead,
        subject="Request for warehousing rates",
        body="Synthetic inquiry. Please send the service sheet for cold storage.",
    )
    _company(
        db,
        northwind,
        name="Northwind Traders",
        website="https://northwind.example",
        industry="Wholesale",
        notes="Synthetic company in a separate organization.",
    )
    _lead(
        db,
        northwind,
        None,
        None,
        outsider,
        title="Catalog refresh",
        status=LeadStatus.new,
        source="Internal",
        notes="Synthetic Northwind lead.",
    )


def _company(
    db: Session,
    organization: Organization,
    *,
    name: str,
    website: str,
    industry: str,
    notes: str,
) -> Company:
    existing = db.scalar(
        select(Company).where(Company.organization_id == organization.id, Company.name == name)
    )
    if existing is not None:
        return existing
    company = Company(
        organization_id=organization.id,
        name=name,
        website=website,
        industry=industry,
        notes=notes,
        origin=Origin.demo,
    )
    db.add(company)
    db.flush()
    return company


def _contact(
    db: Session,
    organization: Organization,
    company: Company,
    *,
    full_name: str,
    email: str,
    title: str,
) -> Contact:
    existing = db.scalar(
        select(Contact).where(Contact.organization_id == organization.id, Contact.email == email)
    )
    if existing is not None:
        return existing
    contact = Contact(
        organization_id=organization.id,
        company_id=company.id,
        full_name=full_name,
        email=email,
        title=title,
        origin=Origin.demo,
    )
    db.add(contact)
    db.flush()
    return contact


def _lead(
    db: Session,
    organization: Organization,
    company: Company | None,
    contact: Contact | None,
    owner: User,
    *,
    title: str,
    status: LeadStatus,
    source: str,
    notes: str,
) -> Lead:
    existing = db.scalar(
        select(Lead).where(Lead.organization_id == organization.id, Lead.title == title)
    )
    if existing is not None:
        return existing
    lead = Lead(
        organization_id=organization.id,
        company_id=company.id if company is not None else None,
        contact_id=contact.id if contact is not None else None,
        owner_user_id=owner.id,
        title=title,
        status=status,
        source=source,
        notes=notes,
        origin=Origin.demo,
    )
    db.add(lead)
    db.flush()
    return lead


def _interaction(
    db: Session, organization: Organization, lead: Lead, author: User, body: str
) -> None:
    existing = db.scalar(
        select(Interaction).where(Interaction.lead_id == lead.id, Interaction.body == body)
    )
    if existing is not None:
        return
    db.add(
        Interaction(
            organization_id=organization.id,
            lead_id=lead.id,
            author_user_id=author.id,
            kind=InteractionKind.note,
            body=body,
            origin=Origin.demo,
        )
    )


def _inquiry(
    db: Session,
    organization: Organization,
    company: Company,
    lead: Lead,
    *,
    subject: str,
    body: str,
) -> None:
    existing = db.scalar(
        select(Inquiry).where(
            Inquiry.organization_id == organization.id, Inquiry.subject == subject
        )
    )
    if existing is not None:
        return
    db.add(
        Inquiry(
            organization_id=organization.id,
            company_id=company.id,
            lead_id=lead.id,
            subject=subject,
            body=body,
            origin=Origin.demo,
        )
    )
