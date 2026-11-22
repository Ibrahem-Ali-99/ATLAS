import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"


class SourceKind(enum.StrEnum):
    document = "document"
    crm = "crm"


MESSAGE_ROLE = Enum(
    MessageRole,
    name="message_role",
    values_callable=lambda roles: [role.value for role in roles],
    native_enum=True,
    create_type=False,
)
SOURCE_KIND = Enum(
    SourceKind,
    name="source_kind",
    values_callable=lambda roles: [role.value for role in roles],
    native_enum=True,
    create_type=False,
)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(MESSAGE_ROLE, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageSource(Base):
    __tablename__ = "message_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[SourceKind] = mapped_column(SOURCE_KIND, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
