from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8b2c6d4f170"
down_revision: str | Sequence[str] | None = "4d8a1c7e3b92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "technical"
TABLE = "text2sql_chat_checkpoints"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("turn_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("conversation_turns.id", ondelete="CASCADE"), nullable=True),
        sa.Column("snapshot", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_technical_text2sql_chat_checkpoints_connection_id", TABLE, ["connection_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_technical_text2sql_chat_checkpoints_conversation_id", TABLE, ["conversation_id"], schema=SCHEMA
    )
    op.create_index("ix_technical_text2sql_chat_checkpoints_expires_at", TABLE, ["expires_at"], schema=SCHEMA)


def downgrade() -> None:
    for column in ("expires_at", "conversation_id", "connection_id"):
        op.drop_index(f"ix_technical_text2sql_chat_checkpoints_{column}", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
