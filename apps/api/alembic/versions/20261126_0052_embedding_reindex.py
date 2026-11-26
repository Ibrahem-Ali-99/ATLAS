"""Stage replacement embeddings without altering the active knowledge index."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261126_0052"
down_revision = "20261126_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embedding_reindexes",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("base", JSONB(), nullable=False),
        sa.Column("encrypted_credentials", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_embedding_reindexes_status", "embedding_reindexes", ["status"])
    op.create_table(
        "embedding_reindex_vectors",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("embedding_reindexes.organization_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("vector", JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("embedding_reindex_vectors")
    op.drop_table("embedding_reindexes")
