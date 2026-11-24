"""Populate and remove a bounded synthetic CRM workspace.

This command is intentionally opt-in.  It only accepts organizations whose slug
starts with ``sample-`` and requires an explicit confirmation flag, so it cannot
silently populate an operational tenant.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import AppError
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
from app.domains.identity.models import Membership, MembershipRole, Organization, User
from app.domains.provenance.origin import Origin

MARKER = "Sample workspace · "
ALLOWED_SLUG_PREFIX = "sample-"


def _require_sample_org(db: Session, slug: str, confirmed: bool) -> Organization:
    if not confirmed:
        raise AppError(400, "confirmation_required", "Pass --confirm-sample-workspace explicitly.")
    if not slug.startswith(ALLOWED_SLUG_PREFIX):
        raise AppError(
            400, "unsafe_organization", "Population is limited to sample-* organizations."
        )
    organization = db.scalar(select(Organization).where(Organization.slug == slug))
    if organization is None:
        raise AppError(404, "organization_not_found", "The sample organization does not exist.")
    return organization


def _owner(db: Session, organization_id: object) -> User:
    owner = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.admin,
            User.is_active.is_(True),
        )
        .order_by(User.created_at)
    )
    if owner is None:
        raise AppError(
            422, "sample_admin_required", "The sample organization needs an active admin."
        )
    return owner


def _company(db: Session, organization_id: object, name: str, industry: str, notes: str) -> Company:
    company = db.scalar(
        select(Company).where(Company.organization_id == organization_id, Company.name == name)
    )
    if company is None:
        company = Company(organization_id=organization_id, name=name, origin=Origin.demo)
        db.add(company)
    company.industry = industry
    company.website = f"https://{name.lower().replace(' ', '-')}.example"
    company.notes = notes
    company.origin = Origin.demo
    db.flush()
    return company


def _contact(
    db: Session, organization_id: object, company: Company, name: str, email: str, title: str
) -> Contact:
    contact = db.scalar(
        select(Contact).where(Contact.organization_id == organization_id, Contact.email == email)
    )
    if contact is None:
        contact = Contact(organization_id=organization_id, email=email, origin=Origin.demo)
        db.add(contact)
    contact.company_id = company.id
    contact.full_name = name
    contact.title = title
    contact.origin = Origin.demo
    db.flush()
    return contact


def _lead(
    db: Session,
    organization_id: object,
    company: Company,
    contact: Contact,
    owner: User,
    title: str,
    status: LeadStatus,
    notes: str,
) -> Lead:
    lead = db.scalar(
        select(Lead).where(Lead.organization_id == organization_id, Lead.title == title)
    )
    if lead is None:
        lead = Lead(organization_id=organization_id, title=title, origin=Origin.demo)
        db.add(lead)
    lead.company_id = company.id
    lead.contact_id = contact.id
    lead.owner_user_id = owner.id
    lead.status = status
    lead.source = "Sample workspace"
    lead.notes = notes
    lead.origin = Origin.demo
    db.flush()
    return lead


def populate(db: Session, organization: Organization) -> dict[str, int]:
    owner = _owner(db, organization.id)
    companies = [
        _company(
            db,
            organization.id,
            f"{MARKER}Harbor Freight",
            "Logistics",
            "Regional warehousing and fulfillment partner.",
        ),
        _company(
            db,
            organization.id,
            f"{MARKER}Northstar Foods",
            "Food manufacturing",
            "Expanding cold-chain distribution across the region.",
        ),
        _company(
            db,
            organization.id,
            f"{MARKER}Cedar Retail Group",
            "Retail",
            "Multi-site retailer evaluating inventory operations.",
        ),
    ]
    contacts = [
        _contact(
            db,
            organization.id,
            companies[0],
            "Mina Patel",
            "mina.patel@harbor-freight.example",
            "Operations Director",
        ),
        _contact(
            db,
            organization.id,
            companies[1],
            "Daniel Okafor",
            "daniel.okafor@northstar-foods.example",
            "Supply Chain Manager",
        ),
        _contact(
            db,
            organization.id,
            companies[2],
            "Sofia Marin",
            "sofia.marin@cedar-retail.example",
            "Commercial Lead",
        ),
    ]
    leads = [
        _lead(
            db,
            organization.id,
            companies[0],
            contacts[0],
            owner,
            f"{MARKER}North pier expansion",
            LeadStatus.qualified,
            "Customer requested capacity and implementation timelines.",
        ),
        _lead(
            db,
            organization.id,
            companies[1],
            contacts[1],
            owner,
            f"{MARKER}Cold-chain discovery",
            LeadStatus.contacted,
            "Discovery call scheduled with the supply chain team.",
        ),
        _lead(
            db,
            organization.id,
            companies[2],
            contacts[2],
            owner,
            f"{MARKER}Inventory visibility pilot",
            LeadStatus.new,
            "Initial interest in a pilot for three retail locations.",
        ),
        _lead(
            db,
            organization.id,
            companies[0],
            contacts[0],
            owner,
            f"{MARKER}Warehouse renewal",
            LeadStatus.won,
            "Renewal confirmed for the current operating footprint.",
        ),
        _lead(
            db,
            organization.id,
            companies[1],
            contacts[1],
            owner,
            f"{MARKER}Packaging review",
            LeadStatus.lost,
            "Opportunity paused after the customer changed priorities.",
        ),
    ]
    inquiries = [
        (
            leads[0],
            companies[0],
            "Capacity for Q3 expansion",
            "Can you share available warehouse capacity and onboarding lead time?",
        ),
        (
            leads[1],
            companies[1],
            "Cold-chain service overview",
            "Please send the service overview for temperature-controlled distribution.",
        ),
        (
            leads[2],
            companies[2],
            "Pilot implementation question",
            "What would a three-location inventory visibility pilot include?",
        ),
    ]
    for lead, company, subject, body in inquiries:
        row = db.scalar(
            select(Inquiry).where(
                Inquiry.organization_id == organization.id, Inquiry.subject == f"{MARKER}{subject}"
            )
        )
        if row is None:
            row = Inquiry(
                organization_id=organization.id, subject=f"{MARKER}{subject}", origin=Origin.demo
            )
            db.add(row)
        row.company_id, row.lead_id, row.body, row.origin = company.id, lead.id, body, Origin.demo
        interaction_body = f"{MARKER}Follow-up recorded for {subject}."
        if (
            db.scalar(
                select(Interaction).where(
                    Interaction.lead_id == lead.id, Interaction.body == interaction_body
                )
            )
            is None
        ):
            db.add(
                Interaction(
                    organization_id=organization.id,
                    lead_id=lead.id,
                    author_user_id=owner.id,
                    kind=InteractionKind.note,
                    body=interaction_body,
                    origin=Origin.demo,
                )
            )
    conversation_title = f"{MARKER}Working with the sample pipeline"
    if (
        db.scalar(
            select(Conversation).where(
                Conversation.organization_id == organization.id,
                Conversation.title == conversation_title,
            )
        )
        is None
    ):
        conversation = Conversation(
            organization_id=organization.id, user_id=owner.id, title=conversation_title
        )
        db.add(conversation)
        db.flush()
        db.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    organization_id=organization.id,
                    role=MessageRole.user,
                    content="Summarize the active sample opportunities.",
                ),
                Message(
                    conversation_id=conversation.id,
                    organization_id=organization.id,
                    role=MessageRole.assistant,
                    content=(
                        "The sample workspace includes new, contacted, qualified, won, "
                        "and lost opportunities across three customer accounts."
                    ),
                ),
            ]
        )
    db.flush()
    return {
        "companies": len(companies),
        "contacts": len(contacts),
        "leads": len(leads),
        "inquiries": len(inquiries),
    }


def purge(db: Session, organization: Organization) -> dict[str, int]:
    company_ids = select(Company.id).where(
        Company.organization_id == organization.id, Company.name.like(f"{MARKER}%")
    )
    lead_ids = select(Lead.id).where(
        Lead.organization_id == organization.id, Lead.title.like(f"{MARKER}%")
    )
    interaction_result = db.execute(delete(Interaction).where(Interaction.lead_id.in_(lead_ids)))
    inquiry_result = db.execute(
        delete(Inquiry).where(
            Inquiry.organization_id == organization.id,
            Inquiry.subject.like(f"{MARKER}%"),
        )
    )
    lead_result = db.execute(
        delete(Lead).where(Lead.organization_id == organization.id, Lead.title.like(f"{MARKER}%"))
    )
    contact_result = db.execute(
        delete(Contact).where(
            Contact.organization_id == organization.id,
            Contact.company_id.in_(company_ids),
        )
    )
    company_result = db.execute(
        delete(Company).where(
            Company.organization_id == organization.id, Company.name.like(f"{MARKER}%")
        )
    )

    def deleted(result: Any) -> int:
        return result.rowcount or 0

    counts = {
        "interactions": deleted(interaction_result),
        "inquiries": deleted(inquiry_result),
        "leads": deleted(lead_result),
        "contacts": deleted(contact_result),
        "companies": deleted(company_result),
    }
    db.execute(
        delete(Conversation).where(
            Conversation.organization_id == organization.id, Conversation.title.like(f"{MARKER}%")
        )
    )
    return counts


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Populate or purge an explicitly designated sample workspace."
    )
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--confirm-sample-workspace", action="store_true")
    parser.add_argument("--purge", action="store_true")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        organization = _require_sample_org(
            db, args.organization_slug, args.confirm_sample_workspace
        )
        result = purge(db, organization) if args.purge else populate(db, organization)
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"workspace_population_failed {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(
        "workspace_population_ok "
        f"mode={'purge' if args.purge else 'populate'} "
        f"organization={args.organization_slug} counts={result}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
