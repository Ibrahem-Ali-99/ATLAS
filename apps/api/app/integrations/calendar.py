import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.automation.models import BookingStatus, CalendarBooking
from app.domains.provenance.origin import Origin
from app.integrations import google_calendar


@dataclass(frozen=True)
class Slot:
    organization_id: uuid.UUID
    lead_id: uuid.UUID
    intent_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    origin: Origin
    provider_calendar_id: str | None = None


class WorkspaceCalendar:
    """Coordinate reservations and their approved external destination."""

    provider = "simulation"

    def book(self, db: Session, slot: Slot) -> CalendarBooking:
        self._lock_organization(db, slot.organization_id)
        if not self.available(db, slot.organization_id, slot.starts_at, slot.ends_at):
            raise AppError(409, "slot_unavailable", "That time is already booked")
        provider = self.provider
        event_id = None
        if slot.provider_calendar_id:
            if slot.origin != Origin.operational:
                raise AppError(
                    409, "calendar_operational_required", "Use an operational CRM record"
                )
            connection = google_calendar.active_connection(db, slot.organization_id)
            if connection is None or connection.calendar_id != slot.provider_calendar_id:
                raise AppError(
                    409, "calendar_account_changed", "Reconnect the approved Google calendar"
                )
            event_id = google_calendar.create_event(connection, slot)
            provider = "google"
        booking = CalendarBooking(
            organization_id=slot.organization_id,
            lead_id=slot.lead_id,
            intent_id=slot.intent_id,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            status=BookingStatus.booked,
            provider=provider,
            origin=slot.origin,
            provider_event_id=event_id,
            provider_calendar_id=slot.provider_calendar_id,
        )
        db.add(booking)
        db.flush()
        return booking

    def cancel(
        self, db: Session, organization_id: uuid.UUID, booking_id: uuid.UUID
    ) -> CalendarBooking:
        self._lock_organization(db, organization_id)
        booking = db.scalar(
            select(CalendarBooking).where(
                CalendarBooking.id == booking_id,
                CalendarBooking.organization_id == organization_id,
            )
        )
        if booking is None:
            raise AppError(404, "not_found", "Resource not found")
        if booking.status == BookingStatus.cancelled:
            return booking
        if booking.provider == "google":
            connection = google_calendar.active_connection(db, organization_id)
            if (
                connection is None
                or not booking.provider_calendar_id
                or not booking.provider_event_id
            ):
                raise AppError(
                    409, "calendar_disconnected", "Reconnect the calendar to cancel this event"
                )
            google_calendar.cancel_event(
                connection, booking.provider_calendar_id, booking.provider_event_id
            )
        elif booking.provider != self.provider:
            raise AppError(
                409, "calendar_provider_unknown", "This calendar booking requires review"
            )
        booking.status = BookingStatus.cancelled
        db.commit()
        db.refresh(booking)
        return booking

    def available(
        self,
        db: Session,
        organization_id: uuid.UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> bool:
        overlap = db.scalar(
            select(CalendarBooking.id).where(
                CalendarBooking.organization_id == organization_id,
                CalendarBooking.status == BookingStatus.booked,
                CalendarBooking.starts_at < ends_at,
                CalendarBooking.ends_at > starts_at,
            )
        )
        return overlap is None

    def _lock_organization(self, db: Session, organization_id: uuid.UUID) -> None:
        google_calendar.lock_workspace(db, organization_id)


def calendar_adapter() -> WorkspaceCalendar:
    return WorkspaceCalendar()
