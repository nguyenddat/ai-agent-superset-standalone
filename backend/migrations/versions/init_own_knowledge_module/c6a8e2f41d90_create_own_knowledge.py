from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6a8e2f41d90"
down_revision: str | Sequence[str] | None = "b9f4d7a2c183"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def base_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    op.create_table(
        "own_knowledge_clarifications", *base_columns(),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("source_session_id", sa.String(255)),
        sa.Column("source_question_id", sa.String(255)),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("answer_fingerprint", sa.String(64)),
        sa.Column("confirmed_entry_ids", sa.JSON(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("connection_id", "user_id", "idempotency_key", name="uq_own_clarification_key"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'dismissed')", name="ck_own_knowledge_clarifications_status_valid"
        ),
    )
    for field in ("connection_id", "user_id"):
        op.create_index(f"ix_own_knowledge_clarifications_{field}", "own_knowledge_clarifications", [field])
    op.create_table(
        "own_knowledge_proposals", *base_columns(),
        sa.Column("clarification_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("own_knowledge_clarifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("concept", sa.String(255)),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("table_id", sa.Uuid(as_uuid=True), sa.ForeignKey("database_tables.id", ondelete="SET NULL")),
        sa.UniqueConstraint("clarification_id", "kind", "normalized_name", name="uq_own_proposal_name"),
        sa.CheckConstraint(
            "kind IN ('glossary', 'metric', 'expert_rule')", name="ck_own_knowledge_proposals_kind_valid"
        ),
    )
    for field in ("clarification_id", "table_id"):
        op.create_index(f"ix_own_knowledge_proposals_{field}", "own_knowledge_proposals", [field])
    op.create_table(
        "own_knowledge_entries", *base_columns(),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("concept", sa.String(255)),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("table_id", sa.Uuid(as_uuid=True), sa.ForeignKey("database_tables.id", ondelete="SET NULL")),
        sa.Column("source_clarification_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("own_knowledge_clarifications.id", ondelete="SET NULL")),
        sa.Column("source_proposal_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("own_knowledge_proposals.id", ondelete="SET NULL")),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text()),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("promoted_kind", sa.String(20)),
        sa.Column("promoted_id", sa.Uuid(as_uuid=True)),
        sa.UniqueConstraint("connection_id", "user_id", "kind", "normalized_name", name="uq_own_entry_name"),
        sa.CheckConstraint("kind IN ('glossary', 'metric', 'expert_rule')", name="ck_own_knowledge_entries_kind_valid"),
        sa.CheckConstraint(
            "review_status IN ('pending', 'kept_own', 'promoted')",
            name="ck_own_knowledge_entries_review_status_valid",
        ),
    )
    for field in ("connection_id", "user_id", "table_id", "source_clarification_id", "source_proposal_id"):
        op.create_index(f"ix_own_knowledge_entries_{field}", "own_knowledge_entries", [field])


def downgrade() -> None:
    for field in ("source_proposal_id", "source_clarification_id", "table_id", "user_id", "connection_id"):
        op.drop_index(f"ix_own_knowledge_entries_{field}", table_name="own_knowledge_entries")
    op.drop_table("own_knowledge_entries")
    for field in ("table_id", "clarification_id"):
        op.drop_index(f"ix_own_knowledge_proposals_{field}", table_name="own_knowledge_proposals")
    op.drop_table("own_knowledge_proposals")
    for field in ("user_id", "connection_id"):
        op.drop_index(f"ix_own_knowledge_clarifications_{field}", table_name="own_knowledge_clarifications")
    op.drop_table("own_knowledge_clarifications")
