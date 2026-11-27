"""The public assistant uses its own credential, budget, and visitor library."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.domains.assistant.inference_guard import assess_public_inference, reset_public_inference
from app.domains.assistant.public_budget import (
    PublicInferenceSpend,
    reserve_public_inference,
    set_public_inference_killed,
)
from app.domains.demo.harbor_catalog import COMPANY_COUNT, visitor_documents
from app.domains.demo.records import populate_visitor
from app.domains.identity.models import MembershipRole, Organization
from app.domains.knowledge.models import Chunk, Document
from app.domains.knowledge.retrieval import search_chunks
from app.integrations.doubles import DeterministicChatClient
from app.integrations.language import (
    OpenAICompatibleChatClient,
    get_chat_client,
    get_embedding_client,
)
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _public(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "public_inference_enabled": True,
        "public_inference_min_interval_seconds": 0,
        "public_llm_authorized": True,
        "public_llm_provider": "groq",
        "public_llm_base_url": "https://api.groq.com/openai/v1",
        "public_llm_api_key": "public-groq-key-not-the-harbor-key",
        "public_llm_model": "openai/gpt-oss-20b",
        "llm_api_key": "harbor-key-must-stay-separate",
        "llm_provider": "groq",
        "llm_base_url": "https://api.groq.com/openai/v1",
        "llm_model": "openai/gpt-oss-20b",
    }
    values.update(overrides)
    return get_settings().model_copy(update=values)


@pytest.fixture(autouse=True)
def _reset_budgets() -> None:
    reset_public_inference()
    yield
    reset_public_inference()
    session = SessionLocal()
    try:
        set_public_inference_killed(session, False)
    finally:
        session.close()


def test_visitor_dataset_includes_the_enterprise_library() -> None:
    titles = [title for title, _filename, _body in visitor_documents()]
    assert "Bonded warehousing overview" in titles
    assert "Rate card effective 1 March 2026" in titles
    assert "Employee handbook" in titles
    assert len(titles) == len(set(titles))


def test_unauthorized_public_chat_does_not_use_the_harbor_key(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"harbor-visitor-{uuid.uuid4().hex[:8]}"
    organization = Organization(name="Harbor visitor", slug=slug)
    db.add(organization)
    db.commit()
    closed = get_settings().model_copy(
        update={
            "public_demo": True,
            "public_inference_enabled": True,
            "public_llm_authorized": False,
            "llm_provider": "groq",
            "llm_base_url": "https://api.groq.com/openai/v1",
            "llm_api_key": "",
            "embedding_api_key": "",
        }
    )
    monkeypatch.setattr("app.integrations.language.get_settings", lambda: closed)
    client = get_chat_client(db, organization.id, public_inference=True)
    assert isinstance(client, DeterministicChatClient)


def test_authorized_public_chat_uses_the_separate_groq_model(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = f"harbor-visitor-{uuid.uuid4().hex[:8]}"
    organization = Organization(name="Harbor visitor", slug=slug)
    db.add(organization)
    db.commit()
    opened = _public()
    monkeypatch.setattr("app.integrations.language.get_settings", lambda: opened)
    client = get_chat_client(db, organization.id, public_inference=True)
    assert isinstance(client, OpenAICompatibleChatClient)
    assert client._settings.llm_model == "openai/gpt-oss-20b"
    assert client._settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert client._settings.llm_api_key == "public-groq-key-not-the-harbor-key"
    assert client._settings.llm_api_key != opened.llm_api_key
    client.ensure_configured()


def test_public_demo_still_refuses_the_harbor_key() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="test",
            secret_key="test-secret-key-must-be-32-chars-min",
            database_url="postgresql+psycopg://atlas:atlas@localhost:5432/atlas_test",
            public_demo=True,
            llm_api_key="harbor-key",
        )


def test_authorized_without_a_public_key_fails_closed() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="test",
            secret_key="test-secret-key-must-be-32-chars-min",
            database_url="postgresql+psycopg://atlas:atlas@localhost:5432/atlas_test",
            public_llm_authorized=True,
            public_llm_api_key="",
        )


def test_persistent_monthly_spend_fails_closed(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = make_organization(db, "Harbor visitor", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    tight = get_settings().model_copy(update={"public_inference_monthly_spend_usd": 0})
    monkeypatch.setattr("app.domains.assistant.public_budget.get_settings", lambda: tight)
    decision = reserve_public_inference(organization.id, "session-spend", "What is the quay fee?")
    assert decision.allowed is False
    assert decision.code == "public_inference_spend_budget"
    stored = db.scalar(
        select(PublicInferenceSpend).where(PublicInferenceSpend.organization_id == organization.id)
    )
    assert stored is None


def test_kill_switch_stops_a_reserved_call(db: Session) -> None:
    organization = make_organization(db, "Harbor visitor", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    set_public_inference_killed(db, True)
    decision = reserve_public_inference(organization.id, "session-killed", "Where is the yard?")
    assert decision.allowed is False
    assert decision.code == "public_inference_disabled"
    set_public_inference_killed(db, False)


def test_daily_reply_cap_is_persistent(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    organization = make_organization(db, "Harbor visitor", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    capped = get_settings().model_copy(update={"public_inference_daily_limit": 1})
    monkeypatch.setattr("app.domains.assistant.public_budget.get_settings", lambda: capped)
    first = reserve_public_inference(organization.id, "daily-a", "Where is the yard?")
    assert first.allowed is True
    second = reserve_public_inference(organization.id, "daily-b", "And the rate?")
    assert second.code == "public_inference_daily_budget"


def test_session_budget_does_not_spend_another_organization(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = make_organization(db, "Harbor visitor", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    second = make_organization(db, "Other visitor", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    enabled = get_settings().model_copy(
        update={"public_inference_enabled": True, "public_inference_min_interval_seconds": 0}
    )

    def _settings() -> Settings:
        return enabled

    monkeypatch.setattr("app.domains.assistant.inference_guard.get_settings", _settings)
    allowed = assess_public_inference(
        "shared-label",
        "Where is the yard?",
        now=1,
        organization_id=first.id,
        persist=True,
    )
    assert allowed.allowed is True
    other = assess_public_inference(
        "shared-label",
        "Where is the yard?",
        now=2,
        organization_id=second.id,
        persist=True,
    )
    assert other.allowed is True
    rows = list(db.scalars(select(PublicInferenceSpend.organization_id)).all())
    assert first.id in rows
    assert second.id in rows


def test_visitor_retrieval_finds_the_rate_card_and_stays_in_the_tenant(
    db: Session, tmp_path
) -> None:
    user = make_user(db, f"visitor-{uuid.uuid4().hex[:8]}@visitors.example")
    organization = make_organization(db, "Harbor & Co.", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    make_membership(db, user, organization, MembershipRole.admin)
    other = make_organization(db, "Other", f"harbor-visitor-{uuid.uuid4().hex[:8]}")
    other_user = make_user(db, f"other-{uuid.uuid4().hex[:8]}@visitors.example")
    make_membership(db, other_user, other, MembershipRole.admin)
    populate_visitor(db, organization, user, storage_root=tmp_path)
    populate_visitor(db, other, other_user, storage_root=tmp_path)
    companies = db.scalars(
        select(Document).where(Document.organization_id == organization.id)
    ).all()
    assert len(companies) > 20
    assert any(item.title == "Rate card effective 1 March 2026" for item in companies)
    embedder = get_embedding_client(db, organization.id)
    hits = search_chunks(
        db,
        organization.id,
        "How much is frozen storage per pallet-week?",
        embedder,
        pipeline="answerable",
    )
    assert any("HBR-FRZ-240" in hit.content or "USD 24.00" in hit.content for hit in hits), [
        (hit.document_title, hit.content[:160]) for hit in hits
    ]
    found = {hit.chunk_id for hit in hits}
    foreign = set(
        db.scalars(select(Chunk.id).where(Chunk.organization_id == other.id)).all()
    )
    assert found.isdisjoint(foreign)
    from app.domains.crm.models import Company

    assert (
        db.scalar(
            select(Company.id).where(
                Company.organization_id == organization.id, Company.name == "Sable Fisheries"
            )
        )
        is not None
    )
    counted = db.scalar(
        select(func.count()).select_from(Company).where(Company.organization_id == organization.id)
    )
    assert counted == COMPANY_COUNT


def test_visitor_cannot_flip_the_kill_switch(client: TestClient) -> None:
    launched = client.post("/api/v1/demo/sessions")
    assert launched.status_code == 200, launched.text
    csrf = launched.json()["csrf_token"]
    organization_id = launched.json()["memberships"][0]["organization_id"]
    refused = client.post(
        f"/api/v1/organizations/{organization_id}/public-inference",
        json={"killed": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "demo_restricted"


def test_administrator_can_stop_public_inference(client: TestClient, db: Session) -> None:
    email = f"ops-{uuid.uuid4().hex[:8]}@example.com"
    user = make_user(db, email)
    organization = make_organization(db, "Atlas Demo", f"atlas-demo-{uuid.uuid4().hex[:8]}")
    make_membership(db, user, organization, MembershipRole.admin)
    session = login(client, email, PASSWORD)
    headers = {"X-CSRF-Token": str(session["csrf_token"])}
    stopped = client.post(
        f"/api/v1/organizations/{organization.id}/public-inference",
        json={"killed": True},
        headers=headers,
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["killed"] is True
    assert "api_key" not in stopped.text
    restored = client.post(
        f"/api/v1/organizations/{organization.id}/public-inference",
        json={"killed": False},
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["killed"] is False


def test_non_visitor_cannot_take_the_public_client(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = make_organization(db, "Atlas Demo", f"atlas-demo-{uuid.uuid4().hex[:8]}")
    opened = _public(public_demo=True, llm_api_key="", embedding_api_key="")
    monkeypatch.setattr("app.integrations.language.get_settings", lambda: opened)
    monkeypatch.setattr("app.integrations.resolver.get_settings", lambda: opened)
    with pytest.raises(AppError) as caught:
        get_chat_client(db, organization.id, public_inference=True)
    assert caught.value.code == "llm_unconfigured"
