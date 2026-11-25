"""add durable workflow schedule timestamps"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0027"
down_revision: str | None = "20261125_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workflow_definitions", sa.Column("next_run_at", sa.DateTime(timezone=True)))
    op.add_column("workflow_definitions", sa.Column("last_run_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("workflow_definitions", "last_run_at")
    op.drop_column("workflow_definitions", "next_run_at")
