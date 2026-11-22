"""add record origin without reclassifying existing rows

Revision ID: 20261122_0011
Revises: 20261122_0010
Create Date: 2026-11-22

Every existing row receives ``unknown``. The migration does not inspect names,
organizations, or dates, and it does not mark historical rows operational.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261122_0011"
down_revision: str | None = "20261122_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "companies",
    "contacts",
    "leads",
    "inquiries",
    "interactions",
    "documents",
    "agent_runs",
    "approvals",
    "workflow_runs",
    "execution_intents",
    "execution_attempts",
    "email_messages",
    "calendar_bookings",
)


def upgrade() -> None:
    origin = postgresql.ENUM(
        "operational",
        "demo",
        "evaluation",
        "unknown",
        name="record_origin",
        create_type=False,
    )
    origin.create(op.get_bind(), checkfirst=True)
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "origin",
                origin,
                server_default="unknown",
                nullable=False,
            ),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "origin")
    postgresql.ENUM(name="record_origin").drop(op.get_bind(), checkfirst=True)
