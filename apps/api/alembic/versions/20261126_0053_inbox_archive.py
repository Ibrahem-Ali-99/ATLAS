"""Retain archived inbox conversations without deleting their messages."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_0053"
down_revision = "20261126_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_conversations",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inbox_conversations",
        sa.Column("archived_by", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inbox_conversations_archived_by_users",
        "inbox_conversations",
        "users",
        ["archived_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_inbox_conversations_archived_at",
        "inbox_conversations",
        ["organization_id", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbox_conversations_archived_at", table_name="inbox_conversations")
    op.drop_constraint(
        "fk_inbox_conversations_archived_by_users",
        "inbox_conversations",
        type_="foreignkey",
    )
    op.drop_column("inbox_conversations", "archived_by")
    op.drop_column("inbox_conversations", "archived_at")
