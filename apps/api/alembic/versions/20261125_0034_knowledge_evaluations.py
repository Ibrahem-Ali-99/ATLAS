"""add organization-scoped knowledge evaluation records"""
# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261125_0034"
down_revision: str | None = "20261125_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_evaluation_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_evaluation_questions_organization_id",
        "knowledge_evaluation_questions",
        ["organization_id"],
    )
    op.create_table(
        "knowledge_evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("retrieved_sources", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_match", sa.Boolean(), nullable=False),
        sa.Column("answer_grounded", sa.Boolean(), nullable=True),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["question_id"], ["knowledge_evaluation_questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_evaluation_runs_organization_id",
        "knowledge_evaluation_runs",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_evaluation_runs_organization_id", table_name="knowledge_evaluation_runs"
    )
    op.drop_table("knowledge_evaluation_runs")
    op.drop_index(
        "ix_knowledge_evaluation_questions_organization_id",
        table_name="knowledge_evaluation_questions",
    )
    op.drop_table("knowledge_evaluation_questions")
