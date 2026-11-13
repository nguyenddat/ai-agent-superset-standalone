from datetime import datetime, timezone
from uuid import uuid7

import sqlalchemy as sa
from alembic import op


revision = "e7b45c29a013"
down_revision = "a4dc134bf7ac"
branch_labels = None
depends_on = None

TABLES = ("database_connections", "database_schemas", "database_tables", "database_columns")
PARENTS = (None, ("connection_id", "database_connections"), ("schema_id", "database_schemas"),
           ("table_id", "database_tables"))


def _snapshot(bind):
    metadata = sa.MetaData()
    return {name: [dict(row) for row in bind.execute(sa.select(sa.Table(name, metadata, autoload_with=bind))).mappings()]
            for name in TABLES}


def _create_tables(uuid_ids):
    key_type = sa.Uuid(as_uuid=True) if uuid_ids else sa.Integer()
    def timestamps():
        return (
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    connection = op.create_table(
        "database_connections",
        sa.Column("id", key_type, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dialect", sa.String(64), nullable=False),
        sa.Column("driver", sa.String(64)),
        sa.Column("uri_ciphertext", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("name", name=op.f("uq_database_connections_name")),
    )
    schema = op.create_table(
        "database_schemas",
        sa.Column("id", key_type, primary_key=True),
        sa.Column("connection_id", key_type, sa.ForeignKey("database_connections.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(timestamps() if uuid_ids else ()),
        sa.UniqueConstraint("connection_id", "name", name=op.f("uq_database_schemas_connection_id")),
    )
    table = op.create_table(
        "database_tables",
        sa.Column("id", key_type, primary_key=True),
        sa.Column("schema_id", key_type, sa.ForeignKey("database_schemas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("table_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(timestamps() if uuid_ids else ()),
        sa.UniqueConstraint("schema_id", "name", name=op.f("uq_database_tables_schema_id")),
    )
    column = op.create_table(
        "database_columns",
        sa.Column("id", key_type, primary_key=True),
        sa.Column("table_id", key_type, sa.ForeignKey("database_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        sa.Column("is_nullable", sa.Boolean(), nullable=False),
        sa.Column("is_primary_key", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("default_value", sa.Text()),
        sa.Column("description", sa.Text()),
        *(timestamps() if uuid_ids else ()),
        sa.UniqueConstraint("table_id", "name", name=op.f("uq_database_columns_table_id")),
    )
    for name, foreign_key in zip(TABLES[1:], ("connection_id", "schema_id", "table_id")):
        op.create_index(op.f(f"ix_{name}_{foreign_key}"), name, [foreign_key])
    return connection, schema, table, column


def _convert(uuid_ids):
    bind = op.get_bind()
    rows = _snapshot(bind)
    mappings = {
        name: {row["id"]: uuid7() if uuid_ids else index
               for index, row in enumerate(rows[name], start=1)}
        for name in TABLES
    }
    for name in reversed(TABLES):
        op.drop_table(name)
    tables = _create_tables(uuid_ids)
    now = datetime.now(timezone.utc)
    for name, table, parent in zip(TABLES, tables, PARENTS):
        converted = []
        for row in rows[name]:
            row["id"] = mappings[name][row["id"]]
            if parent:
                key, parent_name = parent
                row[key] = mappings[parent_name][row[key]]
            if uuid_ids:
                row.setdefault("created_at", now)
                row.setdefault("updated_at", now)
            elif name != TABLES[0]:
                row.pop("created_at", None)
                row.pop("updated_at", None)
            converted.append(row)
        if converted:
            bind.execute(table.insert(), converted)


def upgrade():
    _convert(True)


def downgrade():
    _convert(False)
