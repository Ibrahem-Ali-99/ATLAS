"""store webhook secrets in a text column so the sealed value fits

Revision ID: 20261122_0008
Revises: 20261122_0007
Create Date: 2026-11-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261122_0008"
down_revision: str | None = "20261122_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "webhook_keys",
        "secret",
        existing_type=sa.String(length=128),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "webhook_keys",
        "secret",
        existing_type=sa.Text(),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
