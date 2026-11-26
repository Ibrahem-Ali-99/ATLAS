"""Remember document fingerprints and allow knowledge archival."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_0055"
down_revision = "20261126_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_documents_archived_at", "documents", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_documents_archived_at", table_name="documents")
    op.drop_column("documents", "archived_at")
    op.drop_column("documents", "content_sha256")
