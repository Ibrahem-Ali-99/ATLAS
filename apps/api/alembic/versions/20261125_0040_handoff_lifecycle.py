"""persist staff takeover and explicit AI resume state"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0040"
down_revision: str | None = "20261125_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inbox_conversations", sa.Column("handoff_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("inbox_conversations", sa.Column("handoff_resolved_at", sa.DateTime(timezone=True)))
    op.add_column("inbox_conversations", sa.Column("ai_resumed", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("inbox_conversations", "ai_resumed")
    op.drop_column("inbox_conversations", "handoff_resolved_at")
    op.drop_column("inbox_conversations", "handoff_accepted_at")
