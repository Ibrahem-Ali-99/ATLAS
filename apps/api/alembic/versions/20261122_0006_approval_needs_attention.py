"""add needs_attention to the approval status

Revision ID: 20261122_0006
Revises: 20261122_0005
Create Date: 2026-11-22

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261122_0006"
down_revision: str | None = "20261122_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE approval_status ADD VALUE IF NOT EXISTS 'needs_attention'")


def downgrade() -> None:
    # PostgreSQL cannot remove a single enum label. Downgrade to base drops the type.
    pass
