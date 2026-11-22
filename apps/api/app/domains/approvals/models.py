import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
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


class ActionType(enum.StrEnum):
    create_lead = "create_lead"
    update_lead = "update_lead"
    prepare_customer_response = "prepare_customer_response"
    request_appointment = "request_appointment"


class ApprovalStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    executing = "executing"
    executed = "executed"
    failed = "failed"
    expired = "expired"
    needs_attention = "needs_attention"


ACTION_TYPE = Enum(
    ActionType,
    name="approval_action",
    values_callable=lambda roles: [role.value for role in roles],
    native_enum=True,
    create_type=False,
)
APPROVAL_STATUS = Enum(
    ApprovalStatus,
    name="approval_status",
    values_callable=lambda roles: [role.value for role in roles],
    native_enum=True,
    create_type=False,
)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("run_id", "action_type", name="uq_approvals_run_action"),
        UniqueConstraint("run_id", "position", name="uq_approvals_run_position"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_approvals_payload_hash"),
        CheckConstraint("position >= 0", name="ck_approvals_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(ACTION_TYPE, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(APPROVAL_STATUS, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    execution_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
