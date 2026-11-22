import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.identity.models import MembershipRole
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login


def _org(payload: dict[str, object]) -> str:
    memberships = payload["memberships"]
    assert isinstance(memberships, list)
    first = memberships[0]
    assert isinstance(first, dict)
    return str(first["organization_id"])


def _csrf(payload: dict[str, object]) -> dict[str, str]:
    return {"X-CSRF-Token": str(payload["csrf_token"])}


def test_crm_crud_search_and_tenant_isolation(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)

    company = client.post(
        f"/api/v1/organizations/{org}/companies",
        json={"name": "Harbor & Co.", "industry": "Logistics"},
        headers=headers,
    )
    assert company.status_code == 201, company.text
    company_id = company.json()["id"]
    contact = client.post(
        f"/api/v1/organizations/{org}/contacts",
        json={"full_name": "Mina Patel", "email": "mina@harbor.example", "company_id": company_id},
        headers=headers,
    )
    assert contact.status_code == 201, contact.text
    lead = client.post(
        f"/api/v1/organizations/{org}/leads",
        json={"title": "North pier expansion", "status": "qualified", "company_id": company_id},
        headers=headers,
    )
    assert lead.status_code == 201, lead.text
    assert lead.json()["owner_user_id"] == str(admin.id)
    lead_id = lead.json()["id"]
    note = client.post(
        f"/api/v1/organizations/{org}/leads/{lead_id}/interactions",
        json={"kind": "note", "body": "Asked about warehousing."},
        headers=headers,
    )
    assert note.status_code == 201
    inquiry = client.post(
        f"/api/v1/organizations/{org}/inquiries",
        json={"subject": "Rates", "body": "Send the service sheet.", "lead_id": lead_id},
        headers=headers,
    )
    assert inquiry.status_code == 201

    listed = client.get(
        f"/api/v1/organizations/{org}/leads", params={"q": "pier", "status": "qualified"}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    history = client.get(f"/api/v1/organizations/{org}/leads/{lead_id}/interactions")
    assert history.json()[0]["body"] == "Asked about warehousing."
    missing_csrf = client.post(
        f"/api/v1/organizations/{org}/companies",
        json={"name": "No token"},
    )
    assert missing_csrf.status_code == 403

    client.cookies.clear()
    other = login(client, "outsider@example.org", PASSWORD)
    denied = client.get(f"/api/v1/organizations/{org}/leads/{lead_id}")
    assert denied.status_code == 404
    own = client.get(f"/api/v1/organizations/{_org(other)}/leads")
    assert own.status_code == 200
    assert own.json()["total"] == 0
    assert uuid.UUID(company_id)
