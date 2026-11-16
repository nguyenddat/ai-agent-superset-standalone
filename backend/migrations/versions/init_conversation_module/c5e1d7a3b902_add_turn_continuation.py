from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e1d7a3b902"
down_revision: str | Sequence[str] | None = "a4c2e8f61b37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTINUED_FROM_FK = "fk_conversation_turns_continued_from_conversation_turns"
CONTINUED_FROM_INDEX = "ix_conversation_turns_continued_from"


def upgrade() -> None:
    with op.batch_alter_table("conversation_turns") as batch:
        batch.add_column(sa.Column("clarification_question", sa.Text()))
        batch.add_column(sa.Column("clarification_options", sa.JSON()))
        batch.add_column(sa.Column("continued_from", sa.Uuid(as_uuid=True)))
        batch.add_column(sa.Column("continuation", sa.JSON()))
        batch.create_foreign_key(
            CONTINUED_FROM_FK, "conversation_turns", ["continued_from"], ["id"], ondelete="SET NULL",
        )
        batch.create_index(CONTINUED_FROM_INDEX, ["continued_from"])


def downgrade() -> None:
    with op.batch_alter_table("conversation_turns") as batch:
        batch.drop_index(CONTINUED_FROM_INDEX)
        batch.drop_constraint(CONTINUED_FROM_FK, type_="foreignkey")
        for column in ("continuation", "continued_from", "clarification_options", "clarification_question"):
            batch.drop_column(column)
