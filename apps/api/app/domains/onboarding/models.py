import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrganizationSetup(Base):
    __tablename__ = "organization_setup"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    business_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    completed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentConfiguration(Base):
    __tablename__ = "agent_configurations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    assistant_name: Mapped[str] = mapped_column(
        String(120), nullable=False, default="ATLAS Assistant"
    )
    purpose: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="Help the team understand and act on customer information.",
    )
    tone: Mapped[str] = mapped_column(String(80), nullable=False, default="professional")
    response_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    business_instructions: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    escalation_threshold: Mapped[float] = mapped_column(
        nullable=False, default=0.55, server_default="0.55"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
