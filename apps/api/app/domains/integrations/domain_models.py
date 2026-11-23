import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DomainVerificationStatus(enum.StrEnum):
    pending = "pending"
    verified = "verified"
    failed = "failed"
    revoked = "revoked"


DOMAIN_VERIFICATION_STATUS = Enum(
    DomainVerificationStatus,
    name="domain_verification_status",
    values_callable=lambda values: [value.value for value in values],
    native_enum=True,
    create_type=False,
)


class EmailDomainVerification(Base):
    __tablename__ = "email_domain_verifications"
    __table_args__ = (UniqueConstraint("organization_id", "domain", name="uq_email_domain_org"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_version: Mapped[int] = mapped_column(nullable=False, default=1)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    status: Mapped[DomainVerificationStatus] = mapped_column(
        DOMAIN_VERIFICATION_STATUS, nullable=False, default=DomainVerificationStatus.pending
    )
    dns_records: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    provider_domain_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
