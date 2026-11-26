import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.agents.models import AgentRun, RunStatus
from app.domains.approvals.models import ActionType
from app.domains.approvals.service import create_approval
from app.domains.audit.service import record_event
from app.domains.crm.models import Inquiry, Lead
from app.domains.identity.dependencies import (
    CsrfAdmin,
    CsrfMember,
    CurrentSession,
    CurrentUser,
    DbSession,
    Member,
    require_admin,
    require_member,
)
from app.integrations import google_calendar
from app.integrations.calendar import calendar_adapter

router = APIRouter(tags=["calendar"])
_WORKSPACE = "/organizations/{organization_id}/calendar"


@router.get(f"{_WORKSPACE}/google")
def connection(member: Member, db: DbSession) -> dict[str, bool | str | None]:
    row = google_calendar.active_connection(db, member.organization.id)
    return {
        "available": google_calendar.configured(get_settings()),
        "connected": row is not None,
        "calendar_name": row.calendar_name if row else None,
        "connection_error": row.connection_error if row else None,
    }


@router.post(f"{_WORKSPACE}/google/connect")
def connect(admin: CsrfAdmin, session: CurrentSession, db: DbSession) -> dict[str, str]:
    return {"url": google_calendar.connect_url(db, admin.organization.id, session.id)}


@router.get("/calendar/google/callback")
def callback(
    user: CurrentUser,
    session: CurrentSession,
    db: DbSession,
    state: Annotated[str, Query(min_length=32, max_length=128)],
    code: Annotated[str | None, Query(max_length=2048)] = None,
) -> RedirectResponse:
    authorization = google_calendar.authorization(db, state, session.id)
    require_admin(require_member(authorization.organization_id, user, db))
    target = google_calendar.finish(db, authorization, code)
    return RedirectResponse(
        target,
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post(f"{_WORKSPACE}/google/disconnect")
def disconnect(admin: CsrfAdmin, db: DbSession) -> dict[str, bool]:
    google_calendar.lock_workspace(db, admin.organization.id)
    record_event(db, admin.organization.id, "calendar.disconnected", {}, actor_id=admin.user.id)
    return {"grant_revoked": google_calendar.disconnect(db, admin.organization.id)}


class AvailabilityRequest(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime


@router.post(f"{_WORKSPACE}/availability")
def availability(
    body: AvailabilityRequest, member: CsrfMember, db: DbSession
) -> dict[str, bool | str]:
    try:
        outcome = _availability(body, member, db)
    except AppError:
        db.commit()
        raise
    db.commit()
    return outcome


def _availability(
    body: AvailabilityRequest, member: Member, db: DbSession
) -> dict[str, bool | str]:
    if not timedelta(0) < body.ends_at - body.starts_at <= timedelta(days=7):
        raise AppError(422, "calendar_invalid_slot", "Choose a time range up to seven days")
    organization_id = member.organization.id
    available = calendar_adapter().available(db, organization_id, body.starts_at, body.ends_at)
    row = google_calendar.active_connection(db, organization_id)
    if row is not None:
        try:
            available = google_calendar.available(row, body.starts_at, body.ends_at) and available
        except AppError as exc:
            google_calendar.record_connection_check(db, row, exc.code)
            raise
        google_calendar.record_connection_check(db, row, None)
    return {"available": available, "provider": "google" if row is not None else "workspace"}


class AppointmentRequest(AvailabilityRequest):
    lead_id: uuid.UUID


@router.post(f"{_WORKSPACE}/requests", status_code=201)
def request_appointment(
    body: AppointmentRequest, member: CsrfMember, db: DbSession
) -> dict[str, str]:
    if body.starts_at <= datetime.now(UTC):
        raise AppError(422, "calendar_past_slot", "Choose a future appointment")
    organization_id = member.organization.id
    lead = db.scalar(
        select(Lead).where(
            Lead.id == body.lead_id,
            Lead.organization_id == organization_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        raise AppError(404, "lead_not_found", "Lead not found")
    inquiry = db.scalar(
        select(Inquiry)
        .where(
            Inquiry.organization_id == organization_id,
            Inquiry.lead_id == lead.id,
            Inquiry.archived_at.is_(None),
        )
        .order_by(Inquiry.created_at.desc(), Inquiry.id)
        .limit(1)
    )
    if inquiry is None:
        raise AppError(
            409, "calendar_inquiry_required", "Link a customer inquiry to this lead first"
        )
    google_calendar.lock_workspace(db, organization_id)
    if not _availability(body, member, db)["available"]:
        raise AppError(409, "slot_unavailable", "That time is already booked")
    run = AgentRun(
        organization_id=organization_id,
        inquiry_id=inquiry.id,
        started_by=member.user.id,
        status=RunStatus.awaiting_approval,
        origin=lead.origin,
    )
    db.add(run)
    db.flush()
    approval = create_approval(
        db,
        organization_id=organization_id,
        run_id=run.id,
        requested_by=member.user.id,
        action_type=ActionType.request_appointment,
        position=0,
        payload={
            "lead_id": str(lead.id),
            "body": "Customer appointment requested",
            "starts_at": body.starts_at.isoformat(),
            "ends_at": body.ends_at.isoformat(),
        },
    )
    return {"approval_id": str(approval.id)}
