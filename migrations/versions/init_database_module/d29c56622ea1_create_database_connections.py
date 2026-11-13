"""Create the source database connection registry.

Revision ID: d29c56622ea1
Revises: 6b5f4607c9c0
Create Date: 2026-11-13 09:55:30.472316

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd29c56622ea1'
down_revision: Union[str, Sequence[str], None] = '6b5f4607c9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "database_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dialect", sa.String(length=64), nullable=False),
        sa.Column("driver", sa.String(length=64), nullable=True),
        sa.Column("uri_ciphertext", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_database_connections")),
        sa.UniqueConstraint("name", name=op.f("uq_database_connections_name")),
    )


def downgrade() -> None:
    op.drop_table("database_connections")
