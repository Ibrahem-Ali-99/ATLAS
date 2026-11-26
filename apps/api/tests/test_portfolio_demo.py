from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.approvals.models import Approval, ApprovalStatus
from app.domains.automation.models import (
    CalendarBooking,
    EmailMessage,
    ExecutionIntent,
    IntentStatus,
    WorkflowDefinition,
    WorkflowTask,
)
from app.domains.campaigns.models import Campaign, CampaignDelivery
from app.domains.crm.models import Company
from app.domains.identity.models import Organization
from app.domains.inbox.models import InboxMessage
from app.domains.knowledge.models import Document, DocumentStatus, IngestionJob
from app.domains.provenance.origin import Origin
from app.scripts.portfolio_demo import (
    assert_portfolio_storage,
    assert_portfolio_target,
    assert_sandbox,
    populate_portfolio,
)
from app.scripts.seed import SeedSettings
from tests.test_seed import SEED


def test_only_atlas_portfolio_is_accepted() -> None:
    assert_portfolio_target("postgresql+psycopg://atlas:secret@127.0.0.1:5434/atlas_portfolio")
    for name in ("atlas", "atlas_test", "atlas_e2e", "postgres", ""):
        with pytest.raises(RuntimeError, match="atlas_portfolio"):
            assert_portfolio_target(f"postgresql+psycopg://atlas:secret@127.0.0.1:5434/{name}")


def test_sandbox_refuses_live_providers() -> None:
    blocked = get_settings().model_copy(update={"llm_provider": "groq", "llm_api_key": "present"})
    with pytest.raises(RuntimeError, match="paid chat model"):
        assert_sandbox(blocked)
    paid = get_settings().model_copy(
        update={"billing_provider": "stripe", "stripe_secret_key": "sk"}
    )
    with pytest.raises(RuntimeError, match="payment provider"):
        assert_sandbox(paid)


def test_storage_stays_outside_the_active_upload_directory(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    with pytest.raises(RuntimeError, match="upload store"):
        assert_portfolio_storage(live, live)
    with pytest.raises(RuntimeError, match="upload store"):
        assert_portfolio_storage(live / "nested", live)
    other = assert_portfolio_storage(tmp_path / "portfolio-storage", live)
    assert other == (tmp_path / "portfolio-storage").resolve()


def test_populate_is_idempotent_and_isolated(db: Session, tmp_path: Path) -> None:
    settings = SeedSettings(_env_file=None, **SEED)
    storage = tmp_path / "documents"
    populate_portfolio(db, settings, storage)
    populate_portfolio(db, settings, storage)

    atlas = _company_names(db, "atlas-demo")
    assert atlas == {"Harbor & Co.", "Lumen Freight"}
    assert _company_names(db, "northwind") == {"Northwind Traders"}

    document = db.scalar(select(Document).where(Document.title == "Bonded warehousing overview"))
    assert document is not None
    assert document.origin is Origin.demo
    assert document.status is DocumentStatus.pending
    assert Path(document.storage_path).is_relative_to(storage.resolve())
    assert Path(document.storage_path).read_text(encoding="utf-8").startswith("Harbor & Co.")
    assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0

    workflow = db.scalar(
        select(WorkflowDefinition).where(WorkflowDefinition.slug == "qualified-lead-follow-up")
    )
    assert workflow is not None
    assert workflow.active is False
    campaign = db.scalar(select(Campaign).where(Campaign.name == "Q3 cold-storage briefing"))
    assert campaign is not None
    assert campaign.status == "draft"
    assert campaign.delivery_mode == "sandbox"
    assert db.scalar(select(func.count()).select_from(CampaignDelivery)) == 0
    assert db.scalar(select(func.count()).select_from(EmailMessage)) == 0

    booking = db.scalar(select(CalendarBooking))
    assert booking is not None
    assert booking.provider == "simulation"
    assert booking.provider_event_id is None
    intent = db.get(ExecutionIntent, booking.intent_id)
    assert intent is not None
    assert intent.status is IntentStatus.succeeded
    rejected = db.scalar(select(Approval).where(Approval.status == ApprovalStatus.rejected))
    assert rejected is not None
    assert (
        db.scalar(select(ExecutionIntent).where(ExecutionIntent.approval_id == rejected.id)) is None
    )
    assert db.scalar(select(func.count()).select_from(Approval)) == 2
    assert db.scalar(select(func.count()).select_from(WorkflowTask)) == 3
    assert db.scalar(select(func.count()).select_from(InboxMessage)) == 3
    assert "not sent" in db.scalar(
        select(InboxMessage.body).where(InboxMessage.delivery_status == "draft")
    )


def _company_names(db: Session, slug: str) -> set[str]:
    rows = db.scalars(
        select(Company.name)
        .join(Organization, Organization.id == Company.organization_id)
        .where(Organization.slug == slug)
    )
    return set(rows.all())
