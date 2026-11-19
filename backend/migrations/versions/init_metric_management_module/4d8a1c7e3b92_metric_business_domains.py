from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d8a1c7e3b92"
down_revision: str | Sequence[str] | None = "9b3e6f2a8c51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "metric_domains"
OWNER = "metric_id"
OWNER_TABLE = "metrics"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(OWNER, sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("domain_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            [OWNER], [f"{OWNER_TABLE}.id"], name=op.f(f"fk_{TABLE}_{OWNER}_{OWNER_TABLE}"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["business_domains.id"], name=op.f(f"fk_{TABLE}_domain_id_business_domains"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(OWNER, "domain_id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index(op.f(f"ix_{TABLE}_domain_id"), TABLE, ["domain_id"])


def downgrade() -> None:
    op.drop_index(op.f(f"ix_{TABLE}_domain_id"), table_name=TABLE)
    op.drop_table(TABLE)
