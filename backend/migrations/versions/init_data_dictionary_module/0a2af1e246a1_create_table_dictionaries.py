"""Create the table-level data dictionary.

Revision ID: 0a2af1e246a1
Revises: e7b45c29a013
Create Date: 2026-11-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a2af1e246a1'
down_revision: Union[str, Sequence[str], None] = 'e7b45c29a013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def audit_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
    )


def dictionary_reference(table_name: str) -> tuple[sa.Column, sa.ForeignKeyConstraint]:
    return (
        sa.Column("table_dictionary_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["table_dictionary_id"], ["table_dictionaries.id"],
            name=op.f(f"fk_{table_name}_table_dictionary_id_table_dictionaries"), ondelete="CASCADE",
        ),
    )


def upgrade() -> None:
    op.create_table(
        "table_dictionaries",
        *audit_columns(),
        sa.Column("table_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("grain_description", sa.Text(), nullable=True),
        sa.Column("table_kind", sa.String(length=32), nullable=True),
        sa.Column("layout", sa.String(length=32), server_default="wide", nullable=False),
        sa.Column("indicator_catalog_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("contains_pii", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["table_id"], ["database_tables.id"], name=op.f("fk_table_dictionaries_table_id_database_tables"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["indicator_catalog_id"], ["table_dictionaries.id"],
            name=op.f("fk_table_dictionaries_indicator_catalog_id_table_dictionaries"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_table_dictionaries")),
        sa.UniqueConstraint("table_id", name=op.f("uq_table_dictionaries_table_id")),
    )
    op.create_index(
        op.f("ix_table_dictionaries_indicator_catalog_id"), "table_dictionaries", ["indicator_catalog_id"]
    )

    op.create_table(
        "table_column_roles",
        *audit_columns(),
        *dictionary_reference("table_column_roles"),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("qualifier", sa.String(length=32), nullable=True),
        sa.Column("column_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["column_id"], ["database_columns.id"],
            name=op.f("fk_table_column_roles_column_id_database_columns"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_table_column_roles")),
        sa.UniqueConstraint(
            "table_dictionary_id", "role", "qualifier", name=op.f("uq_table_column_roles_table_dictionary_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(op.f("ix_table_column_roles_table_dictionary_id"), "table_column_roles", ["table_dictionary_id"])
    op.create_index(op.f("ix_table_column_roles_column_id"), "table_column_roles", ["column_id"])

    op.create_table(
        "table_time_grains",
        *audit_columns(),
        *dictionary_reference("table_time_grains"),
        sa.Column("row_kind_value", sa.String(length=255), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("time_grain", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_table_time_grains")),
        sa.UniqueConstraint(
            "table_dictionary_id", "row_kind_value", name=op.f("uq_table_time_grains_table_dictionary_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(op.f("ix_table_time_grains_table_dictionary_id"), "table_time_grains", ["table_dictionary_id"])

    op.create_table(
        "indicator_aggregations",
        *audit_columns(),
        *dictionary_reference("indicator_aggregations"),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("aggregation", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_indicator_aggregations")),
        sa.UniqueConstraint(
            "table_dictionary_id", "source_code", name=op.f("uq_indicator_aggregations_table_dictionary_id")
        ),
    )
    op.create_index(
        op.f("ix_indicator_aggregations_table_dictionary_id"), "indicator_aggregations", ["table_dictionary_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_indicator_aggregations_table_dictionary_id"), table_name="indicator_aggregations")
    op.drop_table("indicator_aggregations")
    op.drop_index(op.f("ix_table_time_grains_table_dictionary_id"), table_name="table_time_grains")
    op.drop_table("table_time_grains")
    op.drop_index(op.f("ix_table_column_roles_column_id"), table_name="table_column_roles")
    op.drop_index(op.f("ix_table_column_roles_table_dictionary_id"), table_name="table_column_roles")
    op.drop_table("table_column_roles")
    op.drop_index(op.f("ix_table_dictionaries_indicator_catalog_id"), table_name="table_dictionaries")
    op.drop_table("table_dictionaries")
