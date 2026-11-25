import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationType(enum.StrEnum):
    chat = "chat"
    embedding = "embedding"
    n8n = "n8n"
    email = "email"
    whatsapp = "whatsapp"


class IntegrationStatus(enum.StrEnum):
    configured = "configured"
    disabled = "disabled"
    verification_failed = "verification_failed"


INTEGRATION_TYPE = Enum(
    IntegrationType,
    name="integration_type",
    values_callable=lambda values: [value.value for value in values],
    native_enum=True,
    create_type=False,
)
INTEGRATION_STATUS = Enum(
    IntegrationStatus,
    name="integration_status",
    values_callable=lambda values: [value.value for value in values],
    native_enum=True,
    create_type=False,
)


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "integration_type", name="uq_integration_configs_org_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    integration_type: Mapped[IntegrationType] = mapped_column(INTEGRATION_TYPE, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[IntegrationStatus] = mapped_column(
        INTEGRATION_STATUS, nullable=False, default=IntegrationStatus.configured
    )
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
