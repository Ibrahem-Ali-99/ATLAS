"""add configurable AI escalation and conversation handoff state"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0037"
down_revision: str | None = "20261125_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_configurations",
        sa.Column("escalation_threshold", sa.Float(), nullable=False, server_default="0.55"),
    )
    op.add_column(
        "conversations",
        sa.Column("needs_human_review", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("conversations", sa.Column("escalation_reason", sa.String(200)))


def downgrade() -> None:
    op.drop_column("conversations", "escalation_reason")
    op.drop_column("conversations", "needs_human_review")
    op.drop_column("agent_configurations", "escalation_threshold")
