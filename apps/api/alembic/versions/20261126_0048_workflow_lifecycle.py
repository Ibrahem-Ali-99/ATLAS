"""Preserve archived workflow definitions and index their execution history."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_0048"
down_revision = "20261126_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_definitions", sa.Column("activated_at", sa.DateTime(timezone=True)))
    op.add_column("workflow_definitions", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE workflow_definitions SET activated_at = updated_at WHERE active")
    op.execute(
        "CREATE INDEX ix_workflow_runs_definition_history "
        "ON workflow_runs (organization_id, (payload->>'workflow_definition_id'), created_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_definition_history", table_name="workflow_runs")
    op.drop_column("workflow_definitions", "archived_at")
    op.drop_column("workflow_definitions", "activated_at")
