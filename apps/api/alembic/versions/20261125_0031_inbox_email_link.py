"""link outbound email messages to inbox conversations"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261125_0031"
down_revision: str | None = "20261125_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("email_messages", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.create_index("ix_email_messages_conversation_id", "email_messages", ["conversation_id"])
    op.create_foreign_key(
        "fk_email_messages_conversation_id",
        "email_messages",
        "inbox_conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_email_messages_conversation_id", "email_messages", type_="foreignkey")
    op.drop_index("ix_email_messages_conversation_id", table_name="email_messages")
    op.drop_column("email_messages", "conversation_id")
