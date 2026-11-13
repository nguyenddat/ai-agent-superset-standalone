"""baseline

Revision ID: 6b5f4607c9c0
Revises:
Create Date: 2026-11-13 09:24:20.545776

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '6b5f4607c9c0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
