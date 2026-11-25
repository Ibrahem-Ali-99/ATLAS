"""track customer requests for human handoff"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0035"
down_revision: str | None = "20261125_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbox_conversations",
        sa.Column("handoff_requested", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("inbox_conversations", sa.Column("handoff_reason", sa.String(200)))


def downgrade() -> None:
    op.drop_column("inbox_conversations", "handoff_reason")
    op.drop_column("inbox_conversations", "handoff_requested")
