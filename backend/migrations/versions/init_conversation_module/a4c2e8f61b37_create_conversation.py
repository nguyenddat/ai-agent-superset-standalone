from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c2e8f61b37"
down_revision: str | Sequence[str] | None = "7e4c1a9b5d32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TURN_STATUSES = (
    "running", "answered", "needs_clarification", "cannot_answer", "join_ambiguous", "join_not_declared", "error",
)
TURN_FLOWS = ("metric", "dataset", "none")
FEEDBACK_RATINGS = ("up", "down")


def base_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def check_in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def upgrade() -> None:
    op.create_table(
        "conversations", *base_columns(),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
    )
    for field in ("connection_id", "user_id", "last_message_at"):
        op.create_index(f"ix_conversations_{field}", "conversations", [field])
    op.create_index(
        "ix_conversations_owner_recent", "conversations", ["user_id", "connection_id", "last_message_at"]
    )
    op.create_table(
        "conversation_turns", *base_columns(),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rewritten_question", sa.Text()),
        sa.Column("answer", sa.Text()),
        sa.Column("flow", sa.String(16)),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("steps", sa.JSON()),
        sa.Column("results", sa.JSON()),
        sa.Column("rewrite", sa.JSON()),
        sa.Column("assumptions", sa.JSON()),
        sa.Column("pii", sa.JSON()),
        sa.Column("dataset_id", sa.Uuid(as_uuid=True)),
        sa.Column("retry_of", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("conversation_turns.id", ondelete="SET NULL")),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("model", sa.String(100)),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_conversation_turn_sequence"),
        sa.CheckConstraint(check_in("status", TURN_STATUSES), name="ck_conversation_turns_status_valid"),
        sa.CheckConstraint(check_in("flow", TURN_FLOWS), name="ck_conversation_turns_flow_valid"),
    )
    for field in ("conversation_id", "retry_of"):
        op.create_index(f"ix_conversation_turns_{field}", "conversation_turns", [field])
    op.create_table(
        "conversation_turn_feedback", *base_columns(),
        sa.Column("turn_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("conversation_turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.UniqueConstraint("turn_id", "user_id", name="uq_conversation_turn_feedback_user"),
        sa.CheckConstraint(check_in("rating", FEEDBACK_RATINGS), name="ck_conversation_turn_feedback_rating_valid"),
    )
    op.create_index("ix_conversation_turn_feedback_turn_id", "conversation_turn_feedback", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_turn_feedback_turn_id", table_name="conversation_turn_feedback")
    op.drop_table("conversation_turn_feedback")
    for field in ("retry_of", "conversation_id"):
        op.drop_index(f"ix_conversation_turns_{field}", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_index("ix_conversations_owner_recent", table_name="conversations")
    for field in ("last_message_at", "user_id", "connection_id"):
        op.drop_index(f"ix_conversations_{field}", table_name="conversations")
    op.drop_table("conversations")
