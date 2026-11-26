"""Harbor receives sealed grants without customer records or old delivery evidence."""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.automation.models import WebhookKey
from app.domains.automation.signatures import open_integration_secret, seal_integration_secret
from app.domains.crm.models import Company
from app.domains.demo.harbor_providers import restore_grants
from app.domains.integrations.calendar_models import GoogleCalendarConnection
from app.domains.integrations.models import IntegrationConfig, IntegrationStatus, IntegrationType
from app.domains.integrations.whatsapp_test import REPLY_ID_KEY
from tests.factories import make_organization


def test_harbor_restore_copies_grants_without_customers_or_delivery_evidence(db: Session) -> None:
    source = make_organization(db, "Atlas Demo", "atlas-demo")
    harbor = make_organization(db, "Harbor & Co.", "harbor-showcase")
    db.add(Company(organization_id=source.id, name="Real customer"))
    db.add(
        IntegrationConfig(
            organization_id=source.id,
            integration_type=IntegrationType.email,
            provider="smtp",
            config={
                "host": "127.0.0.1",
                "port": 1025,
                "from_address": "harbor@example.com",
                "resend_test_recipient": "owner@example.com",
            },
            encrypted_credentials=seal_integration_secret(
                json.dumps(
                    {
                        "resend_api_key": "re_test_placeholder",
                        "resend_test_message_id": str(uuid.uuid4()),
                        "resend_test_recipient": "delivered@resend.dev",
                        "resend_test_verified_at": "2026-01-01T00:00:00+00:00",
                        "resend_test_confirmation": "accepted",
                    }
                )
            ),
            status=IntegrationStatus.configured,
            verified_at=datetime.now(UTC),
        )
    )
    db.add(
        IntegrationConfig(
            organization_id=source.id,
            integration_type=IntegrationType.whatsapp,
            provider="meta",
            config={
                "phone_number_id": "100",
                "business_account_id": "200",
                REPLY_ID_KEY: "wamid.already-sent",
            },
            encrypted_credentials=seal_integration_secret(
                json.dumps({"access_token": "meta-test-token"})
            ),
            status=IntegrationStatus.configured,
            verified_at=datetime.now(UTC),
        )
    )
    db.add(
        GoogleCalendarConnection(
            organization_id=source.id,
            calendar_id="primary",
            calendar_name="Operations",
            encrypted_token=seal_integration_secret("refresh-token"),
            connected_at=datetime.now(UTC),
        )
    )
    db.add(
        WebhookKey(
            organization_id=source.id,
            name="n8n",
            secret=seal_integration_secret("signing-key"),
        )
    )
    db.commit()

    first = restore_grants(db, db)
    second = restore_grants(db, db)

    assert {item.kind: item.status for item in first}["email"] == "copied"
    assert {item.kind: item.status for item in second}["email"] == "already_present"
    assert (
        db.scalar(
            select(func.count()).select_from(Company).where(Company.organization_id == harbor.id)
        )
        == 0
    )
    email = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == harbor.id,
            IntegrationConfig.integration_type == IntegrationType.email,
        )
    )
    assert email is not None
    assert email.verified_at is None
    assert "resend_test_recipient" not in email.config
    opened = json.loads(open_integration_secret(email.encrypted_credentials or ""))
    assert opened["resend_api_key"] == "re_test_placeholder"
    assert "resend_test_message_id" not in opened
    whatsapp = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == harbor.id,
            IntegrationConfig.integration_type == IntegrationType.whatsapp,
        )
    )
    assert whatsapp is not None
    assert whatsapp.verified_at is None
    assert set(whatsapp.config) == {"phone_number_id", "business_account_id"}
    assert {item.kind: item.status for item in first}["google_calendar"] == "blocked"
    assert db.get(GoogleCalendarConnection, harbor.id) is None
    source_calendar = db.get(GoogleCalendarConnection, source.id)
    assert source_calendar is not None
    assert open_integration_secret(source_calendar.encrypted_token or "") == "refresh-token"
    key = db.scalar(select(WebhookKey).where(WebhookKey.organization_id == harbor.id))
    assert key is not None
    assert open_integration_secret(key.secret) == "signing-key"
    assert (
        db.scalar(
            select(func.count()).select_from(Company).where(Company.organization_id == source.id)
        )
        == 1
    )
