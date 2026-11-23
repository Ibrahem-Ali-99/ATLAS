import uuid

from fastapi import APIRouter

from app.domains.approvals import service as approvals
from app.domains.approvals.schemas import ApprovalOut
from app.domains.automation import status
from app.domains.automation.hooks import create_webhook_key
from app.domains.automation.schemas import (
    AutomationSnapshot,
    BookingOut,
    EmailActivityOut,
    WebhookKeyOut,
)
from app.domains.identity.dependencies import CsrfAdmin, DbSession, Member
from app.domains.provenance.origin import DataScope
from app.integrations.calendar import calendar_adapter

router = APIRouter(prefix="/organizations/{organization_id}", tags=["automation"])


@router.get("/automations", response_model=AutomationSnapshot)
def get_automations(
    member: Member, db: DbSession, scope: DataScope = DataScope.operational
) -> AutomationSnapshot:
    return AutomationSnapshot.model_validate(status.snapshot(db, member.organization.id, scope))


@router.get("/email-activity", response_model=list[EmailActivityOut])
def get_email_activity(
    member: Member, db: DbSession, scope: DataScope = DataScope.operational
) -> list[EmailActivityOut]:
    return [
        EmailActivityOut.model_validate(item)
        for item in status._email_activity(db, member.organization.id, scope)
    ]


@router.post("/integrations/webhook-keys", response_model=WebhookKeyOut, status_code=201)
def create_key(member: CsrfAdmin, db: DbSession) -> WebhookKeyOut:
    key, secret = create_webhook_key(db, member.organization.id)
    return WebhookKeyOut(id=key.id, name=key.name, secret=secret)


@router.post("/approvals/{approval_id}/execute", response_model=ApprovalOut)
def execute_approval(approval_id: uuid.UUID, member: CsrfAdmin, db: DbSession) -> ApprovalOut:
    approvals.execute_approved(db, member.organization.id, approval_id)
    approval = approvals.get_approval(db, member.organization.id, approval_id)
    return ApprovalOut.model_validate(approval)


@router.post("/calendar/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: uuid.UUID, member: CsrfAdmin, db: DbSession) -> BookingOut:
    booking = calendar_adapter().cancel(db, member.organization.id, booking_id)
    return BookingOut(
        id=booking.id,
        lead_id=booking.lead_id,
        status=booking.status.value,
        provider=booking.provider,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        provider_event_id=booking.provider_event_id,
    )
