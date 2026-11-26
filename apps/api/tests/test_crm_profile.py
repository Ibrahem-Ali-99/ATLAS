from enum import Enum

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.crm.profile import _channel_label
from app.domains.identity.models import MembershipRole
from app.domains.inbox.models import InboxConversation, InboxStatus
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


def test_duplicate_records_lead_conversion_and_profile(client: TestClient, db: Session) -> None:
    admin = make_user(db, "ada@example.com")
    outsider = make_user(db, "outsider@example.org")
    atlas = make_organization(db, "Atlas Demo", "atlas-demo")
    northwind = make_organization(db, "Northwind", "northwind")
    make_membership(db, admin, atlas, MembershipRole.admin)
    make_membership(db, outsider, northwind, MembershipRole.admin)
    ada = login(client, "ada@example.com", PASSWORD)
    headers = _csrf(ada)
    org = _org(ada)
    base = f"/api/v1/organizations/{org}"

    company = client.post(f"{base}/companies", json={"name": "Harbor & Co."}, headers=headers)
    assert company.status_code == 201, company.text
    company_id = company.json()["id"]
    duplicate = client.post(f"{base}/companies", json={"name": "  harbor & co.  "}, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_company"
    same = client.patch(
        f"{base}/companies/{company_id}", json={"name": "Harbor & Co."}, headers=headers
    )
    assert same.status_code == 200, same.text

    contact = client.post(
        f"{base}/contacts",
        json={"full_name": "Mina Patel", "email": "Mina@Harbor.example", "company_id": company_id},
        headers=headers,
    )
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["id"]
    duplicate_contact = client.post(
        f"{base}/contacts",
        json={"full_name": "Mina Again", "email": "mina@harbor.example"},
        headers=headers,
    )
    assert duplicate_contact.status_code == 409
    assert duplicate_contact.json()["error"]["code"] == "duplicate_contact"

    lead = client.post(
        f"{base}/leads",
        json={"title": "North pier expansion", "company_id": company_id, "contact_id": contact_id},
        headers=headers,
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]
    assert lead.json()["status"] == "new"
    inquiry = client.post(
        f"{base}/inquiries",
        json={"subject": "Rates", "body": "Send the service sheet.", "lead_id": lead_id},
        headers=headers,
    )
    assert inquiry.status_code == 201, inquiry.text
    note = client.post(
        f"{base}/leads/{lead_id}/interactions",
        json={"kind": "call", "body": "Discussed the pier schedule."},
        headers=headers,
    )
    assert note.status_code == 201, note.text
    task = client.post(
        f"{base}/workflow-tasks",
        json={"title": "Send the sheet", "lead_id": lead_id, "priority": "high"},
        headers=headers,
    )
    assert task.status_code == 201, task.text

    converted = client.post(f"{base}/leads/{lead_id}/convert", headers=headers)
    assert converted.status_code == 200, converted.text
    assert converted.json()["created"] is True
    assert converted.json()["stage"] == "new"
    again = client.post(f"{base}/leads/{lead_id}/convert", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["created"] is False
    assert again.json()["id"] == converted.json()["id"]
    refreshed = client.get(f"{base}/leads/{lead_id}")
    assert refreshed.json()["status"] == "qualified"

    lost = client.post(
        f"{base}/leads", json={"title": "Closed pier", "status": "lost"}, headers=headers
    )
    blocked = client.post(f"{base}/leads/{lost.json()['id']}/convert", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "lead_not_convertible"

    profile = client.get(f"{base}/customer-profile", params={"company_id": company_id})
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["subject"]["title"] == "Harbor & Co."
    assert body["contacts"][0]["title"] == "Mina Patel"
    assert body["leads"][0]["title"] == "North pier expansion"
    assert body["inquiries"][0]["title"] == "Rates"
    assert body["opportunities"][0]["title"] == "North pier expansion"
    assert body["tasks"][0]["title"] == "Send the sheet"
    assert body["tasks"][0]["priority"] == "high"
    kinds = {item["kind"] for item in body["activity"]}
    assert {"request", "call", "task"} <= kinds

    titled = client.get(f"{base}/companies", params={"sort": "title"})
    assert titled.status_code == 422
    ordered = client.get(f"{base}/leads", params={"sort": "title"})
    assert ordered.status_code == 200
    assert ordered.json()["items"][0]["title"] == "Closed pier"

    conversation = InboxConversation(
        organization_id=atlas.id,
        contact_id=contact_id,
        lead_id=lead_id,
        subject="Cold storage for the north pier",
        channel="email",
        status=InboxStatus.open,
    )
    db.add(conversation)
    db.commit()
    with_channel = client.get(f"{base}/customer-profile", params={"company_id": company_id})
    assert with_channel.status_code == 200, with_channel.text
    assert with_channel.json()["conversations"][0]["channel"] == "email"

    client.cookies.clear()
    other = login(client, "outsider@example.org", PASSWORD)
    hidden = client.get(
        f"/api/v1/organizations/{_org(other)}/customer-profile", params={"lead_id": lead_id}
    )
    assert hidden.status_code == 404


def test_channel_label_reads_stored_text_and_enum_values() -> None:
    class LegacyChannel(Enum):
        whatsapp = "whatsapp"

    assert _channel_label("email") == "email"
    assert _channel_label(LegacyChannel.whatsapp) == "whatsapp"
