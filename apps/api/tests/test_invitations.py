import uuid

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


def test_resend_replaces_the_invitation_token_and_leave_keeps_the_last_admin(
    client: TestClient, db: Session
) -> None:
    organization = make_organization(db, "Membership Workspace", f"members-{uuid.uuid4().hex[:8]}")
    admin = make_user(db, "members-admin@example.com")
    staff = make_user(db, "members-staff@example.com")
    outsider = make_user(db, "members-outsider@example.com")
    other = make_organization(db, "Other Membership", f"other-members-{uuid.uuid4().hex[:8]}")
    make_membership(db, admin, organization, MembershipRole.admin)
    make_membership(db, outsider, other, MembershipRole.admin)
    session = login(client, admin.email, PASSWORD)
    headers = _csrf(session)
    created = client.post(
        f"/api/v1/organizations/{organization.id}/invitations",
        json={"email": "invitee@example.com"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    original = created.json()["token"]
    resent = client.post(
        f"/api/v1/organizations/{organization.id}/invitations/{created.json()['id']}/resend",
        headers=headers,
    )
    assert resent.status_code == 200, resent.text
    replacement = resent.json()["token"]
    assert replacement != original
    expired = client.post(
        "/api/v1/invitations/accept",
        json={"token": original, "full_name": "Invitee", "password": "correct-horse-2"},
    )
    assert expired.status_code == 400
    make_membership(db, staff, organization, MembershipRole.staff)
    client.cookies.clear()
    staff_session = login(client, staff.email, PASSWORD)
    blocked = client.post(
        f"/api/v1/organizations/{organization.id}/invitations/{created.json()['id']}/resend",
        headers=_csrf(staff_session),
    )
    assert blocked.status_code == 403
    client.cookies.clear()
    outsider_session = login(client, outsider.email, PASSWORD)
    foreign = client.post(
        f"/api/v1/organizations/{organization.id}/invitations/{created.json()['id']}/resend",
        headers=_csrf(outsider_session),
    )
    assert foreign.status_code == 404
    client.cookies.clear()
    colleague_session = login(client, staff.email, PASSWORD)
    left = client.post(
        f"/api/v1/organizations/{organization.id}/leave",
        headers=_csrf(colleague_session),
    )
    assert left.status_code == 204
    client.cookies.clear()
    admin_session = login(client, admin.email, PASSWORD)
    members = client.get(f"/api/v1/organizations/{organization.id}/members")
    assert staff.email not in {item["email"] for item in members.json()}
    last = client.post(
        f"/api/v1/organizations/{organization.id}/leave",
        headers=_csrf(admin_session),
    )
    assert last.status_code == 409
    assert last.json()["error"]["code"] == "last_admin"
