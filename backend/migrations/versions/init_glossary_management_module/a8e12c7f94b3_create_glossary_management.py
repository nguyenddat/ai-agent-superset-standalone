from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8e12c7f94b3"
down_revision: str | Sequence[str] | None = "f6c1a2d937e4"
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
        "glossary_terms", *base_columns(),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("group_name", sa.String(255)),
        sa.UniqueConstraint("connection_id", "normalized_name", name="uq_glossary_term_name"),
    )
    op.create_index("ix_glossary_terms_connection_id", "glossary_terms", ["connection_id"])
    op.create_table(
        "glossary_revisions", *base_columns(),
        sa.Column("term_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("synonyms", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.UniqueConstraint("term_id", "number", name="uq_glossary_revision_number"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'revoked')", name="ck_glossary_revisions_status_valid"),
    )
    op.create_index("ix_glossary_revisions_term_id", "glossary_revisions", ["term_id"])
    op.create_table(
        "glossary_links", *base_columns(),
        sa.Column("revision_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("glossary_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("table_id", sa.Uuid(as_uuid=True), sa.ForeignKey("database_tables.id", ondelete="CASCADE")),
        sa.Column("column_id", sa.Uuid(as_uuid=True), sa.ForeignKey("database_columns.id", ondelete="CASCADE")),
        sa.Column("metric_id", sa.Uuid(as_uuid=True), sa.ForeignKey("metrics.id", ondelete="CASCADE")),
        sa.CheckConstraint("kind IN ('table', 'column', 'metric')", name="ck_glossary_links_kind_valid"),
        sa.CheckConstraint(
            "(kind = 'table' AND table_id IS NOT NULL AND column_id IS NULL AND metric_id IS NULL) OR "
            "(kind = 'column' AND table_id IS NULL AND column_id IS NOT NULL AND metric_id IS NULL) OR "
            "(kind = 'metric' AND table_id IS NULL AND column_id IS NULL AND metric_id IS NOT NULL)",
            name="ck_glossary_links_target_valid",
        ),
        sa.UniqueConstraint("revision_id", "table_id", name="uq_glossary_link_table"),
        sa.UniqueConstraint("revision_id", "column_id", name="uq_glossary_link_column"),
        sa.UniqueConstraint("revision_id", "metric_id", name="uq_glossary_link_metric"),
    )
    op.create_index("ix_glossary_links_revision_id", "glossary_links", ["revision_id"])
    for target in ("table_id", "column_id", "metric_id"):
        op.create_index(f"ix_glossary_links_{target}", "glossary_links", [target])


def downgrade() -> None:
    for target in ("metric_id", "column_id", "table_id"):
        op.drop_index(f"ix_glossary_links_{target}", table_name="glossary_links")
    op.drop_index("ix_glossary_links_revision_id", table_name="glossary_links")
    op.drop_table("glossary_links")
    op.drop_index("ix_glossary_revisions_term_id", table_name="glossary_revisions")
    op.drop_table("glossary_revisions")
    op.drop_index("ix_glossary_terms_connection_id", table_name="glossary_terms")
    op.drop_table("glossary_terms")
