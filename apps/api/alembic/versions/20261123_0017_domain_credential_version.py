"""bind sender-domain evidence to an email credential version

Revision ID: 20261123_0017
Revises: 20261123_0016
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261123_0017"
down_revision: str | None = "20261123_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_domain_verifications",
        sa.Column("credential_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("email_domain_verifications", "credential_version")
