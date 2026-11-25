"""allow manual tasks and add task management fields"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0042"
down_revision: str | None = "20261125_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("workflow_tasks_workflow_run_id_key", "workflow_tasks", type_="unique")
    op.alter_column("workflow_tasks", "workflow_run_id", nullable=True)
    op.add_column("workflow_tasks", sa.Column("opportunity_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_workflow_tasks_opportunity_id",
        "workflow_tasks",
        "opportunities",
        ["opportunity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "workflow_tasks",
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "workflow_tasks",
        sa.Column("source", sa.String(24), nullable=False, server_default="workflow"),
    )


def downgrade() -> None:
    op.drop_column("workflow_tasks", "source")
    op.drop_column("workflow_tasks", "priority")
    op.drop_constraint("fk_workflow_tasks_opportunity_id", "workflow_tasks", type_="foreignkey")
    op.drop_column("workflow_tasks", "opportunity_id")
    op.alter_column("workflow_tasks", "workflow_run_id", nullable=False)
    op.create_unique_constraint(
        "workflow_tasks_workflow_run_id_key", "workflow_tasks", ["workflow_run_id"]
    )
