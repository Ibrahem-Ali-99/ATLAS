"""add opportunity loss reasons"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0043"
down_revision: str | None = "20261125_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pipeline_stages", sa.Column("probability", sa.Float(), nullable=True))
    op.add_column("opportunities", sa.Column("loss_reason", sa.String(240), nullable=True))


def downgrade() -> None:
    op.drop_column("opportunities", "loss_reason")
    op.drop_column("pipeline_stages", "probability")
