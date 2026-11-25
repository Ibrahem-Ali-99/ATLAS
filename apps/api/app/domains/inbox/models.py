# ruff: noqa: E501
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InboxStatus(enum.StrEnum):
    open = "open"
    pending = "pending"
    resolved = "resolved"


STATUS = Enum(InboxStatus, name="inbox_status", native_enum=True, create_type=False)


class InboxConversation(Base):
    __tablename__ = "inbox_conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="email")
    status: Mapped[InboxStatus] = mapped_column(STATUS, nullable=False, default=InboxStatus.open)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    unread_count: Mapped[int] = mapped_column(nullable=False, default=0)
    handoff_requested: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    handoff_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    handoff_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handoff_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_resumed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InboxMessage(Base):
    __tablename__ = "inbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider_message_id", name="uq_inbox_provider_message"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("inbox_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="email")
    delivery_status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")
    provider_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WidgetConfig(Base):
    __tablename__ = "inbox_widget_configs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    allowed_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    appearance: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    welcome_message: Mapped[str] = mapped_column(
        String(500), nullable=False, default="How can we help?"
    )
    operating_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="human_review")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WidgetSession(Base):
    __tablename__ = "inbox_widget_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    widget_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("inbox_widget_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("inbox_conversations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    visitor_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    origin: Mapped[str] = mapped_column(String(300), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
