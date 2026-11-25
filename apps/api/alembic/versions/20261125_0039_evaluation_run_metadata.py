"""store evaluation model metadata and per-case results"""
# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261125_0039"
down_revision: str | None = "20261125_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_evaluation_runs", sa.Column("model_identifier", sa.String(120), nullable=False, server_default="deterministic"))
    op.add_column("knowledge_evaluation_runs", sa.Column("configuration_version", sa.String(120), nullable=False, server_default="default"))
    op.add_column("knowledge_evaluation_runs", sa.Column("case_result", postgresql.JSONB(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("knowledge_evaluation_runs", "case_result")
    op.drop_column("knowledge_evaluation_runs", "configuration_version")
    op.drop_column("knowledge_evaluation_runs", "model_identifier")
