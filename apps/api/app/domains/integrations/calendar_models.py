import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleCalendarConnection(Base):
    __tablename__ = "google_calendar_connections"
    __table_args__ = (
        Index(
            "uq_google_calendar_active_id",
            "calendar_id",
            unique=True,
            postgresql_where=text("encrypted_token IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    calendar_id: Mapped[str] = mapped_column(String(512))
    calendar_name: Mapped[str] = mapped_column(String(200))
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connection_error: Mapped[str | None] = mapped_column(String(80))


class GoogleCalendarAuthorization(Base):
    __tablename__ = "google_calendar_authorizations"

    state_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    encrypted_verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
