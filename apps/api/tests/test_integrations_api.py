from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _admin(client: TestClient, db: Session) -> tuple[str, dict[str, str]]:
    user = make_user(db, "admin@example.com")
    organization = make_organization(db, "Atlas", "atlas-api")
    make_membership(db, user, organization, MembershipRole.admin)
    session = login(client, "admin@example.com", PASSWORD)
    return str(organization.id), {"X-CSRF-Token": str(session["csrf_token"])}


def test_admin_can_configure_without_returning_secret(client: TestClient, db: Session) -> None:
    organization_id, headers = _admin(client, db)
    response = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/chat",
        json={
            "provider": "groq",
            "config": {"base_url": "https://api.groq.com/openai/v1", "model": "test"},
            "credentials": "gsk-test-secret",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_credentials"] is True
    assert "gsk-test-secret" not in response.text


def test_integration_mutation_requires_csrf(client: TestClient, db: Session) -> None:
    organization_id, _ = _admin(client, db)
    response = client.put(
        f"/api/v1/organizations/{organization_id}/integration-configs/chat",
        json={"provider": "groq", "credentials": "secret"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_non_admin_cannot_modify_integration(client: TestClient, db: Session) -> None:
    user = make_user(db, "staff@example.com")
    organization = make_organization(db, "Atlas", "atlas-staff")
    make_membership(db, user, organization, MembershipRole.staff)
    session = login(client, "staff@example.com", PASSWORD)
    response = client.put(
        f"/api/v1/organizations/{organization.id}/integration-configs/chat",
        json={"provider": "groq", "credentials": "secret"},
        headers={"X-CSRF-Token": str(session["csrf_token"])},
    )
    assert response.status_code == 403
