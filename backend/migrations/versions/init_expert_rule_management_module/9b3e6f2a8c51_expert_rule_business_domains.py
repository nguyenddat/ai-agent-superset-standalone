from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b3e6f2a8c51"
down_revision: str | Sequence[str] | None = "e2a7c4d91f36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "expert_rule_domains"
OWNER = "rule_id"
OWNER_TABLE = "expert_rules"


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
    # Free-text groups become memberships of the business domain with the same name; unmatched groups are dropped.
    op.execute(sa.text(
        f"INSERT INTO {TABLE} ({OWNER}, domain_id) "
        f"SELECT o.id, d.id FROM {OWNER_TABLE} o JOIN business_domains d ON lower(d.name) = lower(trim(o.group_name)) "
        "WHERE o.group_name IS NOT NULL"
    ))
    with op.batch_alter_table(OWNER_TABLE) as batch:
        batch.drop_column("group_name")


def downgrade() -> None:
    with op.batch_alter_table(OWNER_TABLE) as batch:
        batch.add_column(sa.Column("group_name", sa.String(255)))
    # A free-text group holds one name, so the alphabetically first domain is kept.
    op.execute(sa.text(
        f"UPDATE {OWNER_TABLE} AS o SET group_name = ("
        f"SELECT d.name FROM {TABLE} j JOIN business_domains d ON d.id = j.domain_id "
        f"WHERE j.{OWNER} = o.id ORDER BY d.name LIMIT 1)"
    ))
    op.drop_index(op.f(f"ix_{TABLE}_domain_id"), table_name=TABLE)
    op.drop_table(TABLE)
