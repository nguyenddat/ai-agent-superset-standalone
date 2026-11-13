"""Create tables and views discovered in source schemas.

Revision ID: 3cbd417d9c61
Revises: c2fecac061e2
Create Date: 2026-11-13 09:59:11.703832

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cbd417d9c61'
down_revision: Union[str, Sequence[str], None] = 'c2fecac061e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_tables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schema_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("table_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["schema_id"], ["database_schemas.id"], name=op.f("fk_database_tables_schema_id_database_schemas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_database_tables")),
        sa.UniqueConstraint("schema_id", "name", name=op.f("uq_database_tables_schema_id")),
    )
    op.create_index(op.f("ix_database_tables_schema_id"), "database_tables", ["schema_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_database_tables_schema_id"), table_name="database_tables")
    op.drop_table("database_tables")
