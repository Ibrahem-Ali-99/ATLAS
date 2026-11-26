import base64
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.automation.signatures import seal_integration_secret
from app.domains.campaigns import dispatch, resend
from app.domains.campaigns.models import Campaign
from app.domains.crm.service import create_contact, create_lead
from app.domains.identity.models import MembershipRole
from app.domains.integrations.domain_models import DomainVerificationStatus, EmailDomainVerification
from app.domains.integrations.models import IntegrationConfig, IntegrationType
from app.integrations.email import DeliveryReceipt, OutboundEmail
from app.integrations.outcomes import OutcomeUncertain
from tests.factories import PASSWORD, make_membership, make_organization, make_user
from tests.helpers import login
from tests.test_crm import _csrf


def test_campaign_preview_uses_the_segment_latest_consent_and_suppression(
    client: TestClient, db: Session
) -> None:
    organization = make_organization(db, "Campaign acceptance", "campaign-acceptance")
    admin = make_user(db, "campaign-admin@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    contacts = {}
    for name, status in (
        ("Eligible", "qualified"),
        ("Revoked", "qualified"),
        ("Suppressed", "qualified"),
        ("Other segment", "new"),
    ):
        contact = create_contact(
            db,
            organization.id,
            {
                "full_name": name,
                "email": f"{name.split()[0].lower()}@example.com",
            },
        )
        create_lead(
            db,
            organization.id,
            admin.id,
            {"title": name, "status": status, "contact_id": contact.id},
        )
        contacts[name] = contact.id
    headers = _csrf(login(client, admin.email, PASSWORD))
    root = f"/api/v1/organizations/{organization.id}"
    for contact_id in contacts.values():
        assert (
            client.post(
                f"{root}/contacts/{contact_id}/marketing-consent",
                params={"source": "acceptance"},
                headers=headers,
            ).status_code
            == 201
        )
    assert (
        client.post(
            f"{root}/contacts/{contacts['Revoked']}/marketing-consent",
            params={
                "source": "unsubscribe",
                "status": "revoked",
            },
            headers=headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{root}/campaign-suppressions",
            json={"email": "SUPPRESSED@example.com"},
            headers=headers,
        ).status_code
        == 201
    )
    segment = client.post(
        f"{root}/segments",
        json={
            "name": "Qualified contacts",
            "conditions": [
                {"field": "lead_status", "operator": "eq", "value": "qualified"},
            ],
        },
        headers=headers,
    )
    assert segment.status_code == 201, segment.text
    campaign = client.post(
        f"{root}/campaigns",
        json={"name": "Warehouse updates", "segment_id": segment.json()["id"]},
        headers=headers,
    )
    assert campaign.status_code == 201, campaign.text
    path = f"{root}/campaigns/{campaign.json()['id']}"
    updated = client.patch(
        path,
        json={"name": "Warehouse updates", "subject": "November update", "body": "Hello."},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert client.get(path).json()["body"] == "Hello."
    preview = client.post(f"{path}/recipients/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "matching_contacts": 3,
        "valid_email": 3,
        "suppressed": 1,
        "consented": 2,
        "missing_consent": 1,
        "eligible": 1,
    }
    contact_path = f"{root}/contacts/{contacts['Eligible']}"
    changed = client.patch(contact_path, json={"email": "new-address@example.com"}, headers=headers)
    assert changed.status_code == 200, changed.text
    consent = client.get(f"{contact_path}/marketing-consent").json()
    assert consent["status"] == "revoked"
    assert consent["source"] == "email_changed"
    assert client.post(f"{path}/recipients/preview").json()["eligible"] == 0


def test_dispatch_rechecks_consent_and_preserves_terminal_outcomes(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization = make_organization(db, "Dispatch", "campaign-dispatch")
    admin = make_user(db, "dispatch-admin@example.com")
    make_membership(db, admin, organization, MembershipRole.admin)
    recipients = {}
    for label in ("accepted", "revoked", "uncertain"):
        contact = create_contact(
            db, organization.id, {"full_name": label, "email": f"{label}@example.com"}
        )
        create_lead(
            db,
            organization.id,
            admin.id,
            {"title": label, "status": "qualified", "contact_id": contact.id},
        )
        recipients[label] = contact.id
    staff = make_user(db, "dispatch-staff@example.com")
    make_membership(db, staff, organization, MembershipRole.staff)
    headers = _csrf(login(client, admin.email, PASSWORD))
    root = f"/api/v1/organizations/{organization.id}"
    for contact_id in recipients.values():
        assert (
            client.post(
                f"{root}/contacts/{contact_id}/marketing-consent",
                params={"source": "acceptance"},
                headers=headers,
            ).status_code
            == 201
        )
    segment = client.post(
        f"{root}/segments",
        json={
            "name": "Eligible contacts",
            "conditions": [
                {"field": "lead_status", "operator": "eq", "value": "qualified"},
            ],
        },
        headers=headers,
    ).json()
    payload = {
        "name": "Dispatch acceptance",
        "segment_id": segment["id"],
        "subject": "Workspace update",
        "body": "Hello.",
    }
    created = client.post(f"{root}/campaigns", json=payload, headers=headers).json()
    path = f"{root}/campaigns/{created['id']}"
    staff_headers = _csrf(login(client, staff.email, PASSWORD))
    assert client.post(f"{path}/schedule", headers=staff_headers, json={}).status_code == 403
    headers = _csrf(login(client, admin.email, PASSWORD))
    assert client.post(f"{path}/schedule", json={}).status_code == 403
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    scheduled = client.post(f"{path}/schedule", headers=headers, json={"scheduled_at": future})
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["deliveries"] == {"queued": 3}
    assert client.post(f"{path}/schedule", headers=headers, json={}).status_code == 409
    assert client.patch(path, headers=headers, json=payload).status_code == 409
    assert dispatch.dispatch_due(db) == 0
    assert (
        client.post(
            f"{root}/contacts/{recipients['revoked']}/marketing-consent",
            params={"source": "acceptance", "status": "revoked"},
            headers=headers,
        ).status_code
        == 201
    )
    campaign = db.get_one(Campaign, uuid.UUID(created["id"]))
    campaign.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    attempts = []
    preference_paths = []

    def sandbox(message: OutboundEmail, **options: object) -> DeliveryReceipt:
        assert options["sandbox_only"] is True
        attempts.append(message.recipient)
        if message.recipient == "uncertain@example.com":
            raise OutcomeUncertain("smtp_timeout")
        assert message.unsubscribe_url is not None
        assert message.unsubscribe_url in message.body
        preference_paths.append("/api/v1/" + message.unsubscribe_url.split("/api/v1/", 1)[1])
        return DeliveryReceipt("accepted-in-test", "sandbox")

    monkeypatch.setattr(dispatch, "send_email", sandbox)
    assert dispatch.dispatch_due(db) == 3
    assert dispatch.dispatch_due(db) == 0
    assert sorted(attempts) == ["accepted@example.com", "uncertain@example.com"]
    completed = client.get(path).json()
    assert completed["status"] == "completed_with_errors"
    assert completed["deliveries"] == {"accepted": 1, "skipped": 1, "needs_attention": 1}
    assert len(client.get(f"{path}/deliveries").json()) == 3
    preference = preference_paths[0]
    assert client.get(preference + "0").status_code == 404
    assert client.get(preference).status_code == 200
    assert client.get(f"{root}/campaign-suppressions").json() == []
    assert client.post(preference).status_code == 400
    assert client.post(preference, data={"confirm": "yes"}).status_code == 200
    assert client.post(preference, data={"List-Unsubscribe": "One-Click"}).status_code == 200
    assert [
        (row["email"], row["reason"]) for row in client.get(f"{root}/campaign-suppressions").json()
    ] == [("accepted@example.com", "unsubscribe")]

    cancelled = client.post(f"{root}/campaigns", json=payload, headers=headers).json()
    pending = f"{root}/campaigns/{cancelled['id']}"
    assert (
        client.post(
            f"{pending}/schedule", headers=headers, json={"scheduled_at": future}
        ).status_code
        == 200
    )
    cancelled = client.post(f"{pending}/cancel", headers=headers).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["deliveries"] == {"cancelled": 1}


def test_live_campaign_pins_resend_transport_and_persists_signed_feedback(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_organization(db, "Live campaign fixture", "live-campaign-fixture")
    second = make_organization(db, "Separate audience", "separate-audience")
    admin = make_user(db, "campaign-feedback@example.com")
    make_membership(db, admin, workspace, MembershipRole.admin)
    make_membership(db, admin, second, MembershipRole.admin)
    headers = _csrf(login(client, admin.email, PASSWORD))
    root = f"/api/v1/organizations/{workspace.id}"
    other = root.replace(str(workspace.id), str(second.id))
    address = "recipient@example.net"
    contact = create_contact(db, workspace.id, {"full_name": "Recipient", "email": address})
    assert (
        client.post(
            f"{root}/contacts/{contact.id}/marketing-consent",
            params={"source": "acceptance"},
            headers=headers,
        ).status_code
        == 201
    )
    segment = client.post(
        f"{root}/segments",
        json={
            "name": "Recipient",
            "conditions": [
                {"field": "contact_email", "operator": "eq", "value": address},
            ],
        },
        headers=headers,
    ).json()
    campaign = client.post(
        f"{root}/campaigns",
        json={
            "name": "Test send",
            "subject": "Update",
            "body": "Hello.",
            "segment_id": segment["id"],
        },
        headers=headers,
    ).json()
    url = f"{root}/campaigns/{campaign['id']}"
    schedule = f"{url}/schedule"
    assert client.post(schedule, json={"delivery_mode": "live"}, headers=headers).status_code == 409
    key = bytes(range(32))
    settings = get_settings()
    monkeypatch.setattr(settings, "email_mode", "live")
    monkeypatch.setattr(settings, "email_live_enabled", True)
    monkeypatch.setattr(settings, "campaign_live_enabled", True)
    monkeypatch.setattr(settings, "campaign_public_url", "https://atlas.example.net")
    monkeypatch.setattr(settings, "campaign_link_secret", "fixture-link-key-" * 3)
    monkeypatch.setattr(
        settings, "resend_campaign_webhook_secret", "whsec_" + base64.b64encode(key).decode()
    )
    assert client.get(f"{root}/campaign-transport").json()["ready"] is False
    db.add_all(
        [
            IntegrationConfig(
                organization_id=workspace.id,
                integration_type=IntegrationType.email,
                provider="smtp",
                config={"from_address": "updates@example.net"},
                encrypted_credentials=seal_integration_secret('{"resend_api_key":"fixture-token"}'),
            ),
            EmailDomainVerification(
                organization_id=workspace.id,
                provider="resend",
                domain="example.net",
                status=DomainVerificationStatus.verified,
            ),
        ]
    )
    db.commit()
    assert client.get(f"{root}/campaign-transport").json()["ready"] is True
    assert client.post(schedule, json={}, headers=headers).status_code == 409
    assert client.post(schedule, json={"delivery_mode": "live"}, headers=headers).status_code == 200
    provider_id = str(uuid.uuid4())

    def post(address: str, **options: dict) -> httpx.Response:
        assert address == "https://api.resend.com/emails"
        assert options["headers"]["Idempotency-Key"]
        assert options["headers"]["Authorization"] == "Bearer fixture-token"
        assert options["json"]["to"] == ["recipient@example.net"]
        assert "/api/v1/campaign-preferences/" in options["json"]["headers"]["List-Unsubscribe"]
        assert options["json"]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        return httpx.Response(200, json={"id": provider_id})

    monkeypatch.setattr(resend.httpx, "post", post)
    assert dispatch.dispatch_due(db) == 1
    assert client.get(url).json()["deliveries"] == {"accepted": 1}
    assert client.get(f"{other}/campaigns/{campaign['id']}/deliveries").status_code == 404
    webhook = "/api/v1/hooks/campaign-delivery/resend"

    def feedback(event: str, *, age: int = 0, invalid: bool = False):
        body = json.dumps({"type": f"email.{event}", "data": {"email_id": provider_id}}).encode()
        event_id = f"msg_{uuid.uuid4().hex}"
        stamp = str(int(datetime.now(UTC).timestamp()) - age)
        signed = hmac.digest(key, f"{event_id}.{stamp}.".encode() + body, "sha256")
        signature = "v1," + base64.b64encode(signed).decode()
        return client.post(
            webhook,
            content=body,
            headers={
                "svix-id": event_id,
                "svix-timestamp": stamp,
                "svix-signature": "v1,invalid" if invalid else signature,
            },
        )

    assert feedback("bounced", invalid=True).status_code == 401
    assert feedback("bounced", age=600).status_code == 401
    assert feedback("delivered").status_code == 204
    assert client.get(url).json()["deliveries"] == {"delivered": 1}
    for event in ("bounced", "bounced", "delivered"):
        assert feedback(event).status_code == 204
    detail = client.get(url).json()
    assert detail["deliveries"] == {"bounced": 1}
    assert detail["status"] == "completed_with_errors"
    assert client.get(f"{other}/campaign-suppressions").json() == []
    assert client.get(f"{root}/campaign-suppressions").json()[0]["reason"] == "bounced"
    assert client.post(f"{url}/recipients/preview").json()["eligible"] == 0
