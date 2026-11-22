"""add a 768-wide embedding column and the model that produced each chunk

Revision ID: 20261122_0010
Revises: 20261122_0009
Create Date: 2026-11-22

The existing vector(1536) column is left in place. Rows already stored there
stay readable as metadata and are not rewritten by this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "20261122_0010"
down_revision: str | None = "20261122_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.add_column("chunks", sa.Column("embedding_768", Vector(768), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding_768")
    op.drop_column("chunks", "embedding_model")
