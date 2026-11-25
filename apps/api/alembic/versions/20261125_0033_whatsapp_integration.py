"""add WhatsApp Cloud integration type"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261125_0033"
down_revision: str | None = "20261125_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE integration_type ADD VALUE IF NOT EXISTS 'whatsapp'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value safely in-place; keep the value
    # available for existing records and let a reviewed schema migration handle it.
    pass
