"""Store Google Calendar grants, short-lived authorizations, and booking ownership."""

import sqlalchemy as sa

from alembic import op

revision = "20261126_0051"
down_revision = "20261126_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_calendar_connections",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("calendar_id", sa.String(512), nullable=False),
        sa.Column("calendar_name", sa.String(200), nullable=False),
        sa.Column("encrypted_token", sa.Text()),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connection_error", sa.String(80)),
    )
    op.create_table(
        "google_calendar_authorizations",
        sa.Column("state_digest", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_google_calendar_active_id",
        "google_calendar_connections",
        ["calendar_id"],
        unique=True,
        postgresql_where=sa.text("encrypted_token IS NOT NULL"),
    )
    op.create_index(
        "ix_google_calendar_authorizations_organization_id",
        "google_calendar_authorizations",
        ["organization_id"],
    )
    op.add_column("calendar_bookings", sa.Column("provider_calendar_id", sa.String(512)))


def downgrade() -> None:
    op.drop_column("calendar_bookings", "provider_calendar_id")
    op.drop_table("google_calendar_authorizations")
    op.drop_table("google_calendar_connections")
