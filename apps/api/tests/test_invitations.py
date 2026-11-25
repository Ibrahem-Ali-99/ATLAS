from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_admin_can_create_and_accept_single_use_staff_invitation(
    client: TestClient, db: Session
) -> None:
    organization = make_organization(db, "Atlas Demo", "atlas-demo")
    admin = make_user(db, "admin@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    session = login(client, admin.email, PASSWORD)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/invitations",
        json={"email": "new@example.com"},
        headers=_csrf(session),
    )
    assert response.status_code == 201
    token = response.json()["token"]
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "full_name": "New User", "password": "correct-horse-2"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["organization_id"] == str(organization.id)
    replay = client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "full_name": "New User", "password": "correct-horse-2"},
    )
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "invalid_invitation"


def test_staff_cannot_create_invitation_and_other_tenant_cannot_use_admin_session(
    client: TestClient, db: Session
) -> None:
    first = make_organization(db, "First", "first")
    second = make_organization(db, "Second", "second")
    staff = make_user(db, "staff@example.com")
    make_membership(db, staff, first, MembershipRole.staff)
    session = login(client, staff.email, PASSWORD)
    forbidden = client.post(
        f"/api/v1/organizations/{first.id}/invitations", json={"email": "x@example.com"}
    )
    assert forbidden.status_code == 403
    missing = client.post(
        f"/api/v1/organizations/{second.id}/invitations",
        json={"email": "x@example.com"},
        headers=_csrf(session),
    )
    assert missing.status_code == 404


def test_invitation_creation_requires_csrf_and_does_not_leak_token(
    client: TestClient, db: Session
) -> None:
    organization = make_organization(db, "Atlas Demo", "atlas-demo")
    admin = make_user(db, "admin@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    login(client, admin.email, PASSWORD)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/invitations",
        json={"email": "x@example.com"},
        headers={"X-CSRF-Token": "bad"},
    )
    assert response.status_code == 403
    assert '"token"' not in response.text.lower()
