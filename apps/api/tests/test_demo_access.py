"""Anonymous demo sessions stay isolated from other organizations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.demo import access
from app.domains.demo.service import cleanup_expired
from app.domains.identity.models import Organization, UserSession
from app.domains.identity.service import upsert_organization
from app.domains.knowledge.models import Document
from app.integrations.doubles import DeterministicChatClient, DeterministicEmbeddingClient
from app.integrations.language import get_chat_client, get_embedding_client


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    access.clear_demo_counters()
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    (tmp_path / "keep.txt").write_text("leave this file", encoding="utf-8")
    return tmp_path


def _launch(client: TestClient) -> tuple[dict[str, object], str]:
    response = client.post("/api/v1/demo/sessions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "password" not in response.text
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "max-age=2700" in cookie
    return body, body["csrf_token"]


def _org(body: dict[str, object]) -> str:
    memberships = body["memberships"]
    assert isinstance(memberships, list) and len(memberships) == 1
    return str(memberships[0]["organization_id"])


def test_anonymous_launch_opens_harbor_and_blocks_credentials(client: TestClient, db) -> None:
    body, csrf = _launch(client)
    organization_id = _org(body)
    slug = str(body["memberships"][0]["organization_slug"])
    assert slug.startswith("harbor-visitor-")
    assert body["demo"] is True
    expires = datetime.fromisoformat(str(body["demo_expires_at"]))
    remaining = expires - datetime.now(UTC)
    assert timedelta(minutes=40) < remaining < timedelta(minutes=50)
    email = str(body["user"]["email"])
    assert email.endswith("@visitors.example")
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "not-a-real-password"},
        ).status_code
        == 401
    )

    companies = client.get(f"/api/v1/organizations/{organization_id}/companies")
    assert companies.status_code == 200
    assert any(item["name"] == "Harbor & Co." for item in companies.json()["items"])
    inbox = client.get(f"/api/v1/organizations/{organization_id}/inbox")
    assert inbox.status_code == 200
    assert "Cold storage for the north pier" in inbox.text
    documents = client.get(f"/api/v1/organizations/{organization_id}/documents")
    assert documents.status_code == 200
    assert "Bonded warehousing overview" in documents.text
    workflows = client.get(f"/api/v1/organizations/{organization_id}/workflow-definitions")
    assert workflows.status_code == 200
    assert "qualified-lead-follow-up" in workflows.text
    analytics = client.get(f"/api/v1/organizations/{organization_id}/analytics")
    assert analytics.status_code == 200
    headers = {"X-CSRF-Token": csrf}
    assert (
        client.get(f"/api/v1/organizations/{organization_id}/integration-configs").status_code
        == 403
    )
    checkout = client.post(
        f"/api/v1/organizations/{organization_id}/billing/checkout",
        json={"plan_code": "starter", "billing_interval": "monthly"},
        headers=headers,
    )
    assert checkout.status_code == 403
    assert checkout.json()["error"]["code"] == "demo_restricted"
    invitations = client.post(
        f"/api/v1/organizations/{organization_id}/invitations",
        json={"email": "person@example.com"},
        headers=headers,
    )
    assert invitations.status_code == 403
    webhook = client.post(
        f"/api/v1/organizations/{organization_id}/integrations/webhook-keys",
        headers=headers,
    )
    assert webhook.status_code == 403
    assert "secret" not in webhook.text
    org_uuid = uuid.UUID(organization_id)
    db.rollback()
    found = db.get(Organization, org_uuid)
    assert found is not None and found.slug.startswith("harbor-visitor-"), found
    assert isinstance(get_chat_client(db, org_uuid), DeterministicChatClient)
    assert isinstance(get_embedding_client(db, org_uuid), DeterministicEmbeddingClient)
    conversations = client.get(f"/api/v1/organizations/{organization_id}/conversations")
    assert conversations.status_code == 200
    conversation_id = conversations.json()[0]["id"]
    reply = client.post(
        f"/api/v1/organizations/{organization_id}/conversations/{conversation_id}/messages",
        json={"content": "Is bonded warehousing available at the north pier?"},
        headers=headers,
    )
    assert reply.status_code == 200, reply.text
    assert "Bonded warehousing is available at the north pier yard." in reply.text


def test_visitors_cannot_read_each_other(client: TestClient) -> None:
    first, _csrf = _launch(client)
    first_cookie = client.cookies.get("atlas_session")
    organization_a = _org(first)
    client.cookies.clear()
    second, _csrf = _launch(client)
    organization_b = _org(second)
    denied = client.get(f"/api/v1/organizations/{organization_a}/companies")
    assert denied.status_code == 404
    client.cookies.clear()
    assert first_cookie is not None
    client.cookies.set("atlas_session", first_cookie)
    denied_b = client.get(f"/api/v1/organizations/{organization_b}/companies")
    assert denied_b.status_code == 404
    own = client.get(f"/api/v1/organizations/{organization_a}/companies")
    assert own.status_code == 200
    assert "Lumen Freight" not in denied.text


def test_restart_replaces_only_the_visitor_workspace(
    client: TestClient, db, isolated_storage: Path
) -> None:
    body, csrf = _launch(client)
    organization_id = uuid.UUID(_org(body))
    document = db.scalar(select(Document).where(Document.organization_id == organization_id))
    assert document is not None
    stored = Path(document.storage_path)
    assert stored.is_file()
    db.rollback()
    restarted = client.post("/api/v1/demo/sessions/restart", headers={"X-CSRF-Token": csrf})
    assert restarted.status_code == 200, restarted.text
    replacement = uuid.UUID(_org(restarted.json()))
    assert replacement != organization_id
    db.expire_all()
    assert db.get(Organization, organization_id) is None
    assert db.get(Organization, replacement) is not None
    assert not stored.exists()
    assert (isolated_storage / "keep.txt").is_file()
    companies = client.get(f"/api/v1/organizations/{replacement}/companies")
    assert any(item["name"] == "Harbor & Co." for item in companies.json()["items"])


def test_expired_session_is_rejected_and_cleanup_keeps_other_organizations(
    client: TestClient, db
) -> None:
    body, _csrf = _launch(client)
    visitor_id = uuid.UUID(_org(body))
    other = upsert_organization(db, name="Northwind Traders", slug="northwind")
    db.commit()
    session = db.scalar(
        select(UserSession).where(UserSession.user_id == uuid.UUID(str(body["user"]["id"])))
    )
    assert session is not None
    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert cleanup_expired(db) == 1
    db.expire_all()
    assert db.get(Organization, visitor_id) is None
    assert db.get(Organization, other.id) is not None


def test_launch_rate_upload_and_request_limits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(access, "LAUNCH_LIMIT", 2)
    monkeypatch.setattr(access, "MAX_REQUESTS", 2)
    first, csrf = _launch(client)
    organization_id = _org(first)
    client.cookies.clear()
    _launch(client)
    client.cookies.clear()
    blocked = client.post("/api/v1/demo/sessions")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    client.cookies.clear()
    access.clear_demo_counters()
    body, csrf = _launch(client)
    organization_id = _org(body)
    headers = {"X-CSRF-Token": csrf}
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    limited = client.get("/api/v1/auth/me")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "demo_limited"
    access.clear_demo_counters()
    oversized = client.post(
        f"/api/v1/organizations/{organization_id}/documents",
        files={"file": ("notes.txt", b"x" * (access.MAX_UPLOAD_BYTES + 1), "text/plain")},
        headers=headers,
    )
    assert oversized.status_code == 422
    assert oversized.json()["error"]["code"] == "demo_limited"


def test_production_without_public_demo_refuses_launch(
    client: TestClient, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")
    monkeypatch.setattr(get_settings(), "public_demo", False)
    response = client.post("/api/v1/demo/sessions")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "demo_unavailable"
    assert db.scalar(select(Organization).where(Organization.slug.like("harbor-visitor-%"))) is None


def test_visitor_organization_uses_deterministic_models(db) -> None:
    organization = Organization(name="Harbor & Co.", slug="harbor-visitor-unitcheck")
    db.add(organization)
    db.commit()
    assert isinstance(get_chat_client(db, organization.id), DeterministicChatClient)
    assert isinstance(get_embedding_client(db, organization.id), DeterministicEmbeddingClient)


def test_campaign_schedule_is_refused(client: TestClient, db) -> None:
    body, csrf = _launch(client)
    organization_id = _org(body)
    from app.domains.campaigns.models import Campaign

    campaign = db.scalar(
        select(Campaign).where(Campaign.organization_id == uuid.UUID(organization_id))
    )
    assert campaign is not None
    campaign_id = campaign.id
    db.rollback()
    response = client.post(
        f"/api/v1/organizations/{organization_id}/campaigns/{campaign_id}/schedule",
        json={"delivery_mode": "sandbox"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "demo_restricted"
    status = db.scalar(select(Campaign.status).where(Campaign.id == campaign_id))
    assert status == "draft"
