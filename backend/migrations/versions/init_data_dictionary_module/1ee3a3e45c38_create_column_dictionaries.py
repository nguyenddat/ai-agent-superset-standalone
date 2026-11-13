"""Create the column-level data dictionary.

Revision ID: 1ee3a3e45c38
Revises: 0a2af1e246a1
Create Date: 2026-11-13 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ee3a3e45c38'
down_revision: Union[str, Sequence[str], None] = '0a2af1e246a1'
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


def column_dictionary_child(table_name: str, value_name: str, value_type: sa.types.TypeEngine) -> None:
    op.create_table(
        table_name,
        *audit_columns(),
        sa.Column("column_dictionary_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(value_name, value_type, nullable=False),
        sa.ForeignKeyConstraint(
            ["column_dictionary_id"], ["column_dictionaries.id"],
            name=op.f(f"fk_{table_name}_column_dictionary_id_column_dictionaries"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")),
        sa.UniqueConstraint("column_dictionary_id", value_name, name=op.f(f"uq_{table_name}_column_dictionary_id")),
    )
    op.create_index(op.f(f"ix_{table_name}_column_dictionary_id"), table_name, ["column_dictionary_id"])


def upgrade() -> None:
    op.create_table(
        "column_dictionaries",
        *audit_columns(),
        sa.Column("column_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_term", sa.Text(), nullable=True),
        sa.Column("semantic_role", sa.String(length=16), nullable=True),
        sa.Column("temporal_kind", sa.String(length=16), nullable=True),
        sa.Column("unit", sa.String(length=128), nullable=True),
        sa.Column("format", sa.String(length=128), nullable=True),
        sa.Column("is_primary_key", sa.Boolean(), nullable=True),
        sa.Column("is_unique", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("referenced_column_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("contains_pii", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["column_id"], ["database_columns.id"], name=op.f("fk_column_dictionaries_column_id_database_columns"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["referenced_column_id"], ["database_columns.id"],
            name=op.f("fk_column_dictionaries_referenced_column_id_database_columns"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_column_dictionaries")),
        sa.UniqueConstraint("column_id", name=op.f("uq_column_dictionaries_column_id")),
    )
    op.create_index(
        op.f("ix_column_dictionaries_referenced_column_id"), "column_dictionaries", ["referenced_column_id"]
    )
    column_dictionary_child("column_aggregations", "aggregation", sa.String(length=16))
    column_dictionary_child("column_synonyms", "synonym", sa.String(length=100))


def downgrade() -> None:
    for table_name in ("column_synonyms", "column_aggregations"):
        op.drop_index(op.f(f"ix_{table_name}_column_dictionary_id"), table_name=table_name)
        op.drop_table(table_name)
    op.drop_index(op.f("ix_column_dictionaries_referenced_column_id"), table_name="column_dictionaries")
    op.drop_table("column_dictionaries")
