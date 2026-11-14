from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6431e2579af"
down_revision: str | Sequence[str] | None = "8c3f26b419d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for field in ("schema_includes", "schema_excludes", "table_includes", "table_excludes"):
        op.add_column("database_connections", sa.Column(field, sa.JSON(), server_default="[]", nullable=False))


def downgrade() -> None:
    for field in ("table_excludes", "table_includes", "schema_excludes", "schema_includes"):
        op.drop_column("database_connections", field)
