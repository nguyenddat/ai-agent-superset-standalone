"""Create columns discovered in source tables and views.

Revision ID: a4dc134bf7ac
Revises: 3cbd417d9c61
Create Date: 2026-11-13 09:59:14.954839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4dc134bf7ac'
down_revision: Union[str, Sequence[str], None] = '3cbd417d9c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_columns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("table_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        sa.Column("is_nullable", sa.Boolean(), nullable=False),
        sa.Column("is_primary_key", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["table_id"], ["database_tables.id"], name=op.f("fk_database_columns_table_id_database_tables"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_database_columns")),
        sa.UniqueConstraint("table_id", "name", name=op.f("uq_database_columns_table_id")),
    )
    op.create_index(op.f("ix_database_columns_table_id"), "database_columns", ["table_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_database_columns_table_id"), table_name="database_columns")
    op.drop_table("database_columns")
