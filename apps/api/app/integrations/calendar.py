import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.automation.models import BookingStatus, CalendarBooking


@dataclass(frozen=True)
class Slot:
    organization_id: uuid.UUID
    lead_id: uuid.UUID
    intent_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime


class SimulatedCalendar:
    """Store bookings in ATLAS. These rows are not events on an external calendar."""

    provider = "simulation"

    def book(self, db: Session, slot: Slot) -> CalendarBooking:
        self._lock_organization(db, slot.organization_id)
        if not self.available(db, slot.organization_id, slot.starts_at, slot.ends_at):
            raise AppError(409, "slot_unavailable", "That time is already booked")
        booking = CalendarBooking(
            organization_id=slot.organization_id,
            lead_id=slot.lead_id,
            intent_id=slot.intent_id,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            status=BookingStatus.booked,
            provider=self.provider,
            provider_event_id=None,
        )
        db.add(booking)
        db.flush()
        return booking

    def cancel(
        self, db: Session, organization_id: uuid.UUID, booking_id: uuid.UUID
    ) -> CalendarBooking:
        booking = db.scalar(
            select(CalendarBooking).where(
                CalendarBooking.id == booking_id,
                CalendarBooking.organization_id == organization_id,
            )
        )
        if booking is None:
            raise AppError(404, "not_found", "Resource not found")
        if booking.provider != self.provider:
            raise AppError(
                409, "invalid_transition", "This booking is not a simulated calendar entry"
            )
        if booking.status == BookingStatus.cancelled:
            return booking
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
        lock_key = int.from_bytes(organization_id.bytes[:4], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


def calendar_adapter() -> SimulatedCalendar:
    return SimulatedCalendar()
