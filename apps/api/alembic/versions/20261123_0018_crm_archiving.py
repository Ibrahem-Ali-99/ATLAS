"""add recoverable archive state to CRM records

Revision ID: 20261123_0018
Revises: 20261123_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261123_0018"
down_revision: str | None = "20261123_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("companies", "contacts", "leads", "inquiries"):
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_archived_at", table, ["archived_at"])


def downgrade() -> None:
    for table in ("inquiries", "leads", "contacts", "companies"):
        op.drop_index(f"ix_{table}_archived_at", table_name=table)
        op.drop_column(table, "archived_at")
