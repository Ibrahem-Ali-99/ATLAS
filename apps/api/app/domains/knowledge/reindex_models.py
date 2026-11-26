import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmbeddingReindex(Base):
    __tablename__ = "embedding_reindexes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    base: Mapped[dict[str, Any]] = mapped_column(JSONB)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReindexVector(Base):
    __tablename__ = "embedding_reindex_vectors"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("embedding_reindexes.organization_id", ondelete="CASCADE"),
        primary_key=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )
    vector: Mapped[list[float]] = mapped_column(JSONB)
