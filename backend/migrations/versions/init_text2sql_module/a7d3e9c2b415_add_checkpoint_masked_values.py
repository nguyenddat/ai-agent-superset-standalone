from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e9c2b415"
down_revision: str | Sequence[str] | None = "f4b8d2a6c913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "technical"
TABLE = "text2sql_chat_checkpoints"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("masked_values", sa.JSON(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column(TABLE, "masked_values", schema=SCHEMA)
