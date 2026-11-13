"""Create schemas discovered in registered databases.

Revision ID: c2fecac061e2
Revises: d29c56622ea1
Create Date: 2026-11-13 09:59:07.417160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2fecac061e2'
down_revision: Union[str, Sequence[str], None] = 'd29c56622ea1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_schemas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["database_connections.id"],
            name=op.f("fk_database_schemas_connection_id_database_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_database_schemas")),
        sa.UniqueConstraint("connection_id", "name", name=op.f("uq_database_schemas_connection_id")),
    )
    op.create_index(op.f("ix_database_schemas_connection_id"), "database_schemas", ["connection_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_database_schemas_connection_id"), table_name="database_schemas")
    op.drop_table("database_schemas")
