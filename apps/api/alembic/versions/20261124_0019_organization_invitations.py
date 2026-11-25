"""add single-use organization invitations

Revision ID: 20261124_0019
Revises: 20261123_0018
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261124_0019"
down_revision: str | None = "20261123_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    role = sa.Enum("staff", name="invitation_role", create_type=False)
    role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_invitations_token_hash", "organization_invitations", ["token_hash"], unique=True)
    op.create_index("ix_org_invitations_org_email", "organization_invitations", ["organization_id", "email"])


def downgrade() -> None:
    op.drop_index("ix_org_invitations_org_email", table_name="organization_invitations")
    op.drop_index("ix_org_invitations_token_hash", table_name="organization_invitations")
    op.drop_table("organization_invitations")
    sa.Enum(name="invitation_role").drop(op.get_bind(), checkfirst=True)
