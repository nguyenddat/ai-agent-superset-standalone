from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d51a78e4b2c0"
down_revision: str | Sequence[str] | None = "b6431e2579af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def base_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "lineage_transformations",
        *base_columns(),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("target_table_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(length=24), server_default="manual", nullable=False),
        sa.ForeignKeyConstraint(
            ["target_table_id"], ["database_tables.id"],
            name=op.f("fk_lineage_transformations_target_table_id_database_tables"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineage_transformations")),
        sa.UniqueConstraint("target_table_id", "name", name=op.f("uq_lineage_transformations_target_table_id")),
    )
    op.create_index(op.f("ix_lineage_transformations_target_table_id"), "lineage_transformations", ["target_table_id"])

    op.create_table(
        "lineage_transformation_inputs",
        *base_columns(),
        sa.Column("transformation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_table_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["transformation_id"], ["lineage_transformations.id"],
            name=op.f("fk_lineage_transformation_inputs_transformation_id_lineage_transformations"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_table_id"], ["database_tables.id"],
            name=op.f("fk_lineage_transformation_inputs_source_table_id_database_tables"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineage_transformation_inputs")),
        sa.UniqueConstraint(
            "transformation_id", "source_table_id", name=op.f("uq_lineage_transformation_inputs_transformation_id"),
        ),
    )
    op.create_index(
        op.f("ix_lineage_transformation_inputs_transformation_id"),
        "lineage_transformation_inputs", ["transformation_id"],
    )
    op.create_index(
        op.f("ix_lineage_transformation_inputs_source_table_id"),
        "lineage_transformation_inputs", ["source_table_id"],
    )

    op.create_table(
        "lineage_column_dependencies",
        *base_columns(),
        sa.Column("transformation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_column_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("target_column_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role IN ('value', 'group', 'join', 'filter')",
            name=op.f("ck_lineage_column_dependencies_role_valid"),
        ),
        sa.CheckConstraint(
            "role <> 'value' OR target_column_id IS NOT NULL",
            name=op.f("ck_lineage_column_dependencies_value_has_target"),
        ),
        sa.ForeignKeyConstraint(
            ["transformation_id"], ["lineage_transformations.id"],
            name=op.f("fk_lineage_column_dependencies_transformation_id_lineage_transformations"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_column_id"], ["database_columns.id"],
            name=op.f("fk_lineage_column_dependencies_source_column_id_database_columns"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_column_id"], ["database_columns.id"],
            name=op.f("fk_lineage_column_dependencies_target_column_id_database_columns"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineage_column_dependencies")),
    )
    for column in ("transformation_id", "source_column_id", "target_column_id"):
        op.create_index(
            op.f(f"ix_lineage_column_dependencies_{column}"), "lineage_column_dependencies", [column],
        )


def downgrade() -> None:
    for column in ("target_column_id", "source_column_id", "transformation_id"):
        op.drop_index(op.f(f"ix_lineage_column_dependencies_{column}"), table_name="lineage_column_dependencies")
    op.drop_table("lineage_column_dependencies")
    op.drop_index(
        op.f("ix_lineage_transformation_inputs_source_table_id"), table_name="lineage_transformation_inputs",
    )
    op.drop_index(
        op.f("ix_lineage_transformation_inputs_transformation_id"), table_name="lineage_transformation_inputs",
    )
    op.drop_table("lineage_transformation_inputs")
    op.drop_index(op.f("ix_lineage_transformations_target_table_id"), table_name="lineage_transformations")
    op.drop_table("lineage_transformations")
