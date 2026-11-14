from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6c1a2d937e4"
down_revision: str | Sequence[str] | None = "d51a78e4b2c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def base_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "superset_users",
        *base_columns(),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name", sa.String(255)),
        sa.Column("email", sa.String(320)),
        sa.UniqueConstraint(
            "source_url", "source_id", name="uq_superset_users_source_url"
        ),
    )
    op.create_table(
        "superset_databases",
        *base_columns(),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("backend", sa.String(64)),
        sa.Column(
            "connection_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("database_connections.id", ondelete="SET NULL"),
        ),
        sa.UniqueConstraint(
            "source_url", "source_id", name="uq_superset_databases_source_url"
        ),
    )
    op.create_index(
        "ix_superset_databases_connection_id", "superset_databases", ["connection_id"]
    )
    op.create_table(
        "metrics",
        *base_columns(),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True)),
        sa.Column("origin", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("format", sa.String(128)),
        sa.Column("currency", sa.String(16)),
        sa.Column("metric_type", sa.String(64)),
        sa.Column("warning_text", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "table_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("database_tables.id", ondelete="SET NULL"),
        ),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("source_metric_id", sa.Integer()),
        sa.Column("source_dataset_id", sa.Integer()),
        sa.Column(
            "source_database_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("superset_databases.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("superset_users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_dataset_owner_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("superset_users.id", ondelete="SET NULL"),
        ),
        sa.Column("source_schema", sa.String(255)),
        sa.Column("source_table", sa.String(255)),
        sa.Column("source_sql", sa.Text()),
        sa.CheckConstraint(
            "origin IN ('manual', 'superset')", name="ck_metrics_origin_valid"
        ),
        sa.UniqueConstraint(
            "source_url", "source_metric_id", name="uq_metrics_source_metric"
        ),
    )
    for column in (
        "table_id",
        "source_database_id",
        "source_user_id",
        "source_dataset_owner_id",
    ):
        op.create_index(f"ix_metrics_{column}", "metrics", [column])


def downgrade() -> None:
    for column in (
        "source_dataset_owner_id",
        "source_user_id",
        "source_database_id",
        "table_id",
    ):
        op.drop_index(f"ix_metrics_{column}", table_name="metrics")
    op.drop_table("metrics")
    op.drop_index(
        "ix_superset_databases_connection_id", table_name="superset_databases"
    )
    op.drop_table("superset_databases")
    op.drop_table("superset_users")
