from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b8d2a6c913"
down_revision: str | Sequence[str] | None = "e8b2c6d4f170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversation_turns") as batch:
        batch.add_column(sa.Column("views", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("conversation_turns") as batch:
        batch.drop_column("views")
