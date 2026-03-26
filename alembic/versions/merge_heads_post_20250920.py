"""Merge heads after is_system_agent flags

Revision ID: merge_heads_post_20250920
Revises: 20250920_000001, f4b599b897f2
Create Date: 2025-09-20 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'merge_heads_post_20250920'
down_revision: Union[str, Sequence[str], None] = ('20250920_000001', 'f4b599b897f2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Schema merge only; no-op."""
    pass


def downgrade() -> None:
    """No-op for merge revision."""
    pass


