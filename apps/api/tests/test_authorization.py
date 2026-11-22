import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def test_protected_organization_routes_require_authentication(client: TestClient) -> None:
    organization_id = uuid.uuid4()
    paths = [
        "/api/v1/organizations",
        f"/api/v1/organizations/{organization_id}",
        f"/api/v1/organizations/{organization_id}/workspace",
        f"/api/v1/organizations/{organization_id}/admin",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthenticated"


def test_member_sees_only_their_organizations(client: TestClient, db: Session) -> None:
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    member = make_user(db, "member@example.com", full_name="Member")
    outsider = make_user(db, "outsider@example.org", full_name="Outsider")
    make_membership(db, member, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    login(client, "member@example.com", PASSWORD)

    own = client.get(f"/api/v1/organizations/{atlas.id}")
    assert own.status_code == 200
    assert own.json()["slug"] == "atlas-demo"
    assert own.json()["role"] == "admin"

    other = client.get(f"/api/v1/organizations/{northwind.id}")
    missing = client.get(f"/api/v1/organizations/{uuid.uuid4()}")
    assert other.status_code == 404
    assert missing.status_code == 404
    assert other.json()["error"] == missing.json()["error"]

    spoofed = client.get(
        f"/api/v1/organizations/{northwind.id}",
        headers={"X-Organization-Id": str(atlas.id)},
    )
    assert spoofed.status_code == 404

    listing = client.get("/api/v1/organizations")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["organizations"]] == [str(atlas.id)]


def test_staff_can_open_workspace_but_not_admin(client: TestClient, db: Session) -> None:
    organization = make_organization(db, "Atlas Demo", "atlas-demo")
    staff = make_user(db, "staff@example.com")
    make_membership(db, staff, organization, MembershipRole.staff)
    login(client, "staff@example.com", PASSWORD)

    workspace = client.get(f"/api/v1/organizations/{organization.id}/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["access"] == "member"
    assert workspace.json()["role"] == "staff"

    admin = client.get(f"/api/v1/organizations/{organization.id}/admin")
    assert admin.status_code == 403
    assert admin.json()["error"]["code"] == "forbidden"

    spoofed_role = client.get(f"/api/v1/organizations/{organization.id}/admin?role=admin")
    assert spoofed_role.status_code == 403


def test_admin_can_open_admin_route(client: TestClient, db: Session) -> None:
    organization = make_organization(db, "Atlas Demo", "atlas-demo")
    admin = make_user(db, "admin@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    login(client, "admin@example.com", PASSWORD)

    response = client.get(f"/api/v1/organizations/{organization.id}/admin")
    assert response.status_code == 200
    assert response.json()["access"] == "admin"
    assert response.json()["role"] == "admin"


def test_admin_of_another_organization_is_not_a_member(client: TestClient, db: Session) -> None:
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    admin = make_user(db, "admin@example.com")
    make_membership(db, admin, atlas, MembershipRole.admin)
    login(client, "admin@example.com", PASSWORD)

    response = client.get(f"/api/v1/organizations/{northwind.id}/admin")
    assert response.status_code == 404
    workspace = client.get(f"/api/v1/organizations/{northwind.id}/workspace")
    assert workspace.status_code == 404


def test_invalid_organization_id_is_rejected(client: TestClient, db: Session) -> None:
    make_user(db, "admin@example.com")
    login(client, "admin@example.com", PASSWORD)
    response = client.get("/api/v1/organizations/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
