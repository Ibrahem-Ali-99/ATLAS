"""add evaluation scenario expectations"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0038"
down_revision: str | None = "20261125_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_evaluation_questions",
        sa.Column("scenario", sa.String(40), nullable=False, server_default="grounded"),
    )
    op.add_column(
        "knowledge_evaluation_questions",
        sa.Column("expected_behavior", sa.String(80), nullable=False, server_default="answer"),
    )


def downgrade() -> None:
    op.drop_column("knowledge_evaluation_questions", "expected_behavior")
    op.drop_column("knowledge_evaluation_questions", "scenario")
