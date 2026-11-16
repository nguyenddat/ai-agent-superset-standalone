from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3b7f19a5e24"
down_revision: str | Sequence[str] | None = "c6a8e2f41d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "technical"
TABLE = "text2sql_ingestion_jobs"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("connection_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("result", sa.JSON()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'superseded')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "source IN ('event', 'schedule', 'manual')", name="source_valid"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_technical_text2sql_ingestion_jobs_connection_id", TABLE, ["connection_id"], schema=SCHEMA)
    op.create_index("ix_text2sql_ingestion_jobs_claim", TABLE, ["status", "run_after"], schema=SCHEMA)
    op.create_index(
        "uq_text2sql_ingestion_jobs_pending", TABLE, ["connection_id", "topic"], schema=SCHEMA,
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_text2sql_ingestion_jobs_pending", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_text2sql_ingestion_jobs_claim", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_technical_text2sql_ingestion_jobs_connection_id", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
