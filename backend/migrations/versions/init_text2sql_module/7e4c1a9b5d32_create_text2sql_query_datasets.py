from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e4c1a9b5d32"
down_revision: str | Sequence[str] | None = "d3b7f19a5e24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "technical"
TABLE = "text2sql_query_datasets"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("root_table_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_ids", sa.JSON(), nullable=False),
        sa.Column("edge_ids", sa.JSON(), nullable=False),
        sa.Column("from_sql", sa.Text(), nullable=False),
        sa.Column("selected_column_ids", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "connection_id", "signature", "root_table_id", name="uq_text2sql_query_datasets_connection_id"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_technical_text2sql_query_datasets_connection_id", TABLE, ["connection_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_technical_text2sql_query_datasets_connection_id", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
