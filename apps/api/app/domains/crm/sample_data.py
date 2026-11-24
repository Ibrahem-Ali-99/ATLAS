"""Clearly synthetic CRM rows for the local seed. Not production data."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.assistant.models import Conversation, Message, MessageRole
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
        notes="Regional warehousing and fulfillment partner.",
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
        notes="Customer asked about warehousing capacity and onboarding timelines.",
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
        body="Please send the service sheet for cold storage.",
    )
    for title, status, source, notes in (
        (
            "Cold storage expansion",
            LeadStatus.contacted,
            "Referral",
            "Evaluating temperature-controlled storage for a Q3 launch.",
        ),
        (
            "Regional fulfillment partnership",
            LeadStatus.new,
            "Partner referral",
            "Needs an initial discovery call about regional fulfillment.",
        ),
        (
            "Warehouse renewal",
            LeadStatus.won,
            "Existing customer",
            "Renewal confirmed for the current operating footprint.",
        ),
        (
            "Packaging services review",
            LeadStatus.lost,
            "Outbound",
            "Opportunity paused after the customer changed priorities.",
        ),
    ):
        extra_lead = _lead(
            db,
            atlas,
            harbor,
            contact,
            admin,
            title=title,
            status=status,
            source=source,
            notes=notes,
        )
        _interaction(db, atlas, extra_lead, admin, f"Follow-up recorded for {title}.")
    _inquiry(
        db,
        atlas,
        harbor,
        lead,
        subject="Cold storage availability for Q3",
        body="Could you confirm whether cold storage capacity is available this quarter?",
    )
    _inquiry(
        db,
        atlas,
        harbor,
        lead,
        subject="Request for fulfillment capabilities",
        body="We would like to understand your regional fulfillment and packaging support.",
    )
    _conversation(
        db,
        atlas,
        admin,
        title="Getting started with ATLAS",
        user_text="What can ATLAS help me with?",
        assistant_text=(
            "ATLAS can explain this workspace, find CRM and knowledge records, and guide "
            "approved agent workflows. Company facts are answered from retrieved evidence."
        ),
    )
    _company(
        db,
        northwind,
        name="Northwind Traders",
        website="https://northwind.example",
        industry="Wholesale",
        notes="Wholesale partner with a separate workspace relationship.",
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
        notes="Initial catalog refresh discussion.",
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


def _conversation(
    db: Session,
    organization: Organization,
    user: User,
    *,
    title: str,
    user_text: str,
    assistant_text: str,
) -> None:
    existing = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == organization.id,
            Conversation.user_id == user.id,
            Conversation.title == title,
        )
    )
    if existing is not None:
        return
    conversation = Conversation(
        organization_id=organization.id,
        user_id=user.id,
        title=title,
    )
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            Message(
                conversation_id=conversation.id,
                organization_id=organization.id,
                role=MessageRole.user,
                content=user_text,
            ),
            Message(
                conversation_id=conversation.id,
                organization_id=organization.id,
                role=MessageRole.assistant,
                content=assistant_text,
            ),
        ]
    )
