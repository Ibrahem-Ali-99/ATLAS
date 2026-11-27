"""The Harbor demonstration is stored data, and visitor quotas ignore it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.domains.automation.models import (
    CalendarBooking,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowTask,
)
from app.domains.campaigns.models import Campaign, CampaignDelivery
from app.domains.crm.models import Company, Contact, Lead, Opportunity
from app.domains.demo.harbor_catalog import (
    APPOINTMENT_COUNT,
    COMPANY_COUNT,
    CONTACT_COUNT,
    CONVERSATION_COUNT,
    LEAD_COUNT,
    LEAD_NOTE,
    OPPORTUNITY_COUNT,
    SPAN_DAYS,
    TASK_COUNT,
    WORKFLOW_COUNT,
    visitor_documents,
)
from app.domains.inbox.models import InboxConversation, InboxMessage
from app.domains.knowledge.models import Document, EvaluationQuestion
from app.domains.provenance.origin import Origin
from app.scripts.harbor_demonstration import assert_harbor_target, assert_sandbox


def _launch(client: TestClient) -> tuple[str, str]:
    response = client.post("/api/v1/demo/sessions")
    assert response.status_code == 200, response.text
    body = response.json()
    organization_id = body["memberships"][0]["organization_id"]
    return str(organization_id), str(body["csrf_token"])


def test_harbor_command_refuses_other_databases() -> None:
    with pytest.raises(RuntimeError, match="atlas_harbor"):
        assert_harbor_target("postgresql+psycopg://localhost/atlas")
    with pytest.raises(RuntimeError, match="atlas_harbor"):
        assert_harbor_target("postgresql+psycopg://localhost/atlas_portfolio")


def test_harbor_command_refuses_live_providers() -> None:
    settings = get_settings()
    original = settings.email_live_enabled
    settings.email_live_enabled = True
    try:
        with pytest.raises(RuntimeError, match="live email"):
            assert_sandbox(settings)
    finally:
        settings.email_live_enabled = original


def test_visitor_workspace_is_a_connected_harbor_dataset(client: TestClient, db) -> None:
    organization_id, csrf = _launch(client)
    org = uuid.UUID(organization_id)
    headers = {"X-CSRF-Token": csrf}

    companies = client.get(
        f"/api/v1/organizations/{organization_id}/companies", params={"page_size": 100}
    )
    assert companies.status_code == 200, companies.text
    assert companies.json()["total"] == COMPANY_COUNT
    assert any(item["name"] == "Harbor & Co." for item in companies.json()["items"])
    assert all(item["origin"] == "demo" for item in companies.json()["items"])

    leads = client.get(f"/api/v1/organizations/{organization_id}/leads", params={"page_size": 100})
    assert leads.json()["total"] == LEAD_COUNT
    assert {item["status"] for item in leads.json()["items"]} >= {
        "new",
        "contacted",
        "qualified",
        "unqualified",
        "won",
        "lost",
    }
    pier = next(item for item in leads.json()["items"] if item["title"] == "North pier expansion")
    assert pier["origin"] == "demo"

    contacts = client.get(
        f"/api/v1/organizations/{organization_id}/contacts", params={"page_size": 100}
    )
    assert contacts.json()["total"] == CONTACT_COUNT
    assert any(item["email"] == "mina.patel@harbor.example" for item in contacts.json()["items"])

    opportunities = client.get(f"/api/v1/organizations/{organization_id}/opportunities")
    assert len(opportunities.json()) == OPPORTUNITY_COUNT
    assert {item["currency"] for item in opportunities.json()} >= {"USD", "EUR"}

    inbox = client.get(f"/api/v1/organizations/{organization_id}/inbox")
    assert len(inbox.json()) == CONVERSATION_COUNT
    assert "Cold storage for the north pier" in inbox.text
    assert "No message has left this workspace." in inbox.text

    documents = client.get(
        f"/api/v1/organizations/{organization_id}/documents", params={"page_size": 20}
    )
    assert documents.json()["total"] == len(visitor_documents())
    assert all(item["origin"] == "demo" for item in documents.json()["items"])

    workflows = client.get(f"/api/v1/organizations/{organization_id}/workflow-definitions")
    assert workflows.status_code == 200, workflows.text
    bodies = workflows.json()
    assert len(bodies) == WORKFLOW_COUNT
    assert all(item["active"] is False for item in bodies)
    follow_up = next(item for item in bodies if item["slug"] == "qualified-lead-follow-up")
    history = client.get(
        f"/api/v1/organizations/{organization_id}/workflow-definitions/{follow_up['id']}/runs"
    )
    assert history.status_code == 200, history.text
    assert any(item["branch"] == "matched" for item in history.json())
    assert any(item["branch"] == "otherwise" for item in history.json())

    campaigns = client.get(f"/api/v1/organizations/{organization_id}/campaigns")
    recorded = next(item for item in campaigns.json() if item["name"] == "Yard safety bulletin")
    detail = client.get(f"/api/v1/organizations/{organization_id}/campaigns/{recorded['id']}")
    assert detail.json()["status"] == "recorded"
    assert detail.json()["deliveries"].get("simulated", 0) >= 1
    assert detail.json()["deliveries"].get("queued", 0) == 0
    assert "accepted" not in detail.json()["deliveries"]

    analytics = client.get(
        f"/api/v1/organizations/{organization_id}/analytics",
        params={"scope": "all", "period": "90d"},
    )
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["companies_total"] == COMPANY_COUNT
    assert analytics.json()["leads_total"] == LEAD_COUNT
    operational = client.get(
        f"/api/v1/organizations/{organization_id}/analytics",
        params={"scope": "operational"},
    )
    assert operational.json()["leads_total"] == 0

    questions = client.get(
        f"/api/v1/organizations/{organization_id}/knowledge/evaluations/questions"
    )
    bonded = next(
        item
        for item in questions.json()
        if item["question"] == "Is bonded warehousing available at the north pier?"
    )
    handoff = next(item for item in questions.json() if item["expected_behavior"] == "handoff")
    grounded = client.post(
        f"/api/v1/organizations/{organization_id}/knowledge/evaluations/questions/{bonded['id']}/run",
        headers=headers,
    )
    assert grounded.status_code == 200, grounded.text
    assert grounded.json()["evidence_match"] is True
    handed = client.post(
        f"/api/v1/organizations/{organization_id}/knowledge/evaluations/questions/{handoff['id']}/run",
        headers=headers,
    )
    assert handed.status_code == 200, handed.text
    assert handed.json()["answer_grounded"] is True

    uploaded = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        files={"file": ("visitor-note.txt", b"A note the visitor added.", "text/plain")},
        data={"origin": "operational"},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text

    db.rollback()
    assert (
        db.scalar(select(func.count()).select_from(Company).where(Company.organization_id == org))
        == COMPANY_COUNT
    )
    assert (
        db.scalar(select(func.count()).select_from(Contact).where(Contact.organization_id == org))
        == CONTACT_COUNT
    )
    assert (
        db.scalar(select(func.count()).select_from(Lead).where(Lead.organization_id == org))
        == LEAD_COUNT
    )
    assert (
        db.scalar(
            select(func.count()).select_from(Opportunity).where(Opportunity.organization_id == org)
        )
        == OPPORTUNITY_COUNT
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(InboxConversation)
            .where(InboxConversation.organization_id == org)
        )
        == CONVERSATION_COUNT
    )
    drafts = db.scalar(
        select(func.count())
        .select_from(InboxMessage)
        .where(
            InboxMessage.organization_id == org,
            InboxMessage.delivery_status == "draft",
        )
    )
    assert drafts == CONVERSATION_COUNT
    assert (
        db.scalar(
            select(func.count())
            .select_from(WorkflowTask)
            .where(WorkflowTask.organization_id == org)
        )
        == TASK_COUNT
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(CalendarBooking)
            .where(CalendarBooking.organization_id == org)
        )
        == APPOINTMENT_COUNT
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(CalendarBooking)
            .where(
                CalendarBooking.organization_id == org,
                CalendarBooking.provider == "simulation",
                CalendarBooking.provider_event_id.is_(None),
            )
        )
        == APPOINTMENT_COUNT
    )
    oldest = db.scalar(select(func.min(Lead.created_at)).where(Lead.organization_id == org))
    assert oldest is not None
    assert oldest <= datetime.now(UTC) - timedelta(days=90)
    assert oldest >= datetime.now(UTC) - timedelta(days=SPAN_DAYS + 1)
    assert (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.organization_id == org, Document.origin == Origin.demo)
        )
        == len(visitor_documents())
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(WorkflowDefinition)
            .where(WorkflowDefinition.organization_id == org, WorkflowDefinition.active.is_(True))
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count()).select_from(WorkflowRun).where(WorkflowRun.organization_id == org)
        )
        >= WORKFLOW_COUNT
    )
    queued = db.scalar(
        select(func.count())
        .select_from(CampaignDelivery)
        .join(Campaign, Campaign.id == CampaignDelivery.campaign_id)
        .where(Campaign.organization_id == org, CampaignDelivery.status == "queued")
    )
    assert queued == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(EvaluationQuestion)
            .where(EvaluationQuestion.organization_id == org)
        )
        == 5
    )
    assert LEAD_NOTE
