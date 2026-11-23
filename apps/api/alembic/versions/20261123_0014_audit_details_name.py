"""avoid SQLAlchemy Declarative metadata name collision

Revision ID: 20261123_0014
Revises: 20261123_0013
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261123_0014"
down_revision: str | None = "20261123_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_events", "metadata", new_column_name="details")


def downgrade() -> None:
    op.alter_column("audit_events", "details", new_column_name="metadata")
