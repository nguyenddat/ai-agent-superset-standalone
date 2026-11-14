from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c3f26b419d0"
down_revision: str | Sequence[str] | None = "1ee3a3e45c38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def audit_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
    )


def upgrade() -> None:
    op.create_table(
        "data_layers",
        *audit_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("level", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_layers")),
        sa.UniqueConstraint("name", name=op.f("uq_data_layers_name")),
    )
    op.add_column("table_dictionaries", sa.Column("layer_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_table_dictionaries_layer_id_data_layers"), "table_dictionaries", "data_layers",
        ["layer_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_table_dictionaries_layer_id"), "table_dictionaries", ["layer_id"])

    op.create_table(
        "business_domains",
        *audit_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_domains")),
        sa.UniqueConstraint("name", name=op.f("uq_business_domains_name")),
    )
    op.create_table(
        "business_domain_tables",
        sa.Column("domain_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("table_dictionary_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["business_domains.id"],
            name=op.f("fk_business_domain_tables_domain_id_business_domains"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["table_dictionary_id"], ["table_dictionaries.id"],
            name=op.f("fk_business_domain_tables_table_dictionary_id_table_dictionaries"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("domain_id", "table_dictionary_id", name=op.f("pk_business_domain_tables")),
    )
    op.create_index(
        op.f("ix_business_domain_tables_table_dictionary_id"), "business_domain_tables", ["table_dictionary_id"]
    )

    for table_name in ("business_canvases", "lineage_canvases"):
        op.create_table(
            table_name,
            *audit_columns(),
            sa.Column("connection_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("layout", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(
                ["connection_id"], ["database_connections.id"],
                name=op.f(f"fk_{table_name}_connection_id_database_connections"), ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")),
            sa.UniqueConstraint("connection_id", name=op.f(f"uq_{table_name}_connection_id")),
        )

    op.create_table(
        "lineage_edges",
        *audit_columns(),
        sa.Column("source_table_dictionary_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("target_table_dictionary_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_table_dictionary_id"], ["table_dictionaries.id"],
            name=op.f("fk_lineage_edges_source_table_dictionary_id_table_dictionaries"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_table_dictionary_id"], ["table_dictionaries.id"],
            name=op.f("fk_lineage_edges_target_table_dictionary_id_table_dictionaries"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineage_edges")),
        sa.UniqueConstraint(
            "source_table_dictionary_id", "target_table_dictionary_id", "kind",
            name=op.f("uq_lineage_edges_source_table_dictionary_id"),
        ),
    )
    op.create_index(op.f("ix_lineage_edges_source_table_dictionary_id"), "lineage_edges", ["source_table_dictionary_id"])
    op.create_index(op.f("ix_lineage_edges_target_table_dictionary_id"), "lineage_edges", ["target_table_dictionary_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_lineage_edges_target_table_dictionary_id"), table_name="lineage_edges")
    op.drop_index(op.f("ix_lineage_edges_source_table_dictionary_id"), table_name="lineage_edges")
    op.drop_table("lineage_edges")
    op.drop_table("lineage_canvases")
    op.drop_table("business_canvases")
    op.drop_index(op.f("ix_business_domain_tables_table_dictionary_id"), table_name="business_domain_tables")
    op.drop_table("business_domain_tables")
    op.drop_table("business_domains")
    op.drop_index(op.f("ix_table_dictionaries_layer_id"), table_name="table_dictionaries")
    op.drop_constraint(op.f("fk_table_dictionaries_layer_id_data_layers"), "table_dictionaries", type_="foreignkey")
    op.drop_column("table_dictionaries", "layer_id")
    op.drop_table("data_layers")
