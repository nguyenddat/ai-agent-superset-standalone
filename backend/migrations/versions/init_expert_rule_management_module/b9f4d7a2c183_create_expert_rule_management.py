from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9f4d7a2c183"
down_revision: str | Sequence[str] | None = "a8e12c7f94b3"
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
        "expert_rules", *base_columns(),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("group_name", sa.String(255)),
        sa.UniqueConstraint("connection_id", "normalized_name", name="uq_expert_rule_name"),
    )
    op.create_index("ix_expert_rules_connection_id", "expert_rules", ["connection_id"])
    op.create_index("ix_expert_rules_table_id", "expert_rules", ["table_id"])
    op.create_table(
        "expert_rule_revisions", *base_columns(),
        sa.Column("rule_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("expert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("exceptions", sa.JSON(), nullable=False),
        sa.Column("examples", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.UniqueConstraint("rule_id", "number", name="uq_expert_rule_revision_number"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'revoked')", name="ck_expert_rule_revisions_status_valid"),
    )
    op.create_index("ix_expert_rule_revisions_rule_id", "expert_rule_revisions", ["rule_id"])
    op.create_table(
        "expert_rule_glossary_links", *base_columns(),
        sa.Column("revision_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("expert_rule_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("glossary_revision_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("glossary_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("revision_id", "term_id", name="uq_expert_rule_glossary_link"),
    )
    for field in ("revision_id", "term_id", "glossary_revision_id"):
        op.create_index(f"ix_expert_rule_glossary_links_{field}", "expert_rule_glossary_links", [field])
    op.create_table(
        "expert_rule_metric_links", *base_columns(),
        sa.Column("revision_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("expert_rule_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.UniqueConstraint("revision_id", "metric_id", name="uq_expert_rule_metric_link"),
    )
    for field in ("revision_id", "metric_id"):
        op.create_index(f"ix_expert_rule_metric_links_{field}", "expert_rule_metric_links", [field])


def downgrade() -> None:
    for field in ("metric_id", "revision_id"):
        op.drop_index(f"ix_expert_rule_metric_links_{field}", table_name="expert_rule_metric_links")
    op.drop_table("expert_rule_metric_links")
    for field in ("glossary_revision_id", "term_id", "revision_id"):
        op.drop_index(f"ix_expert_rule_glossary_links_{field}", table_name="expert_rule_glossary_links")
    op.drop_table("expert_rule_glossary_links")
    op.drop_index("ix_expert_rule_revisions_rule_id", table_name="expert_rule_revisions")
    op.drop_table("expert_rule_revisions")
    op.drop_index("ix_expert_rules_table_id", table_name="expert_rules")
    op.drop_index("ix_expert_rules_connection_id", table_name="expert_rules")
    op.drop_table("expert_rules")
