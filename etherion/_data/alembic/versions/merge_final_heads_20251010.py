"""Final merge of all heads

Revision ID: merge_final_heads_20251010
Revises: c32c9ff9ca19, merge_20250114_heads
Create Date: 2025-10-10 08:43:40

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'merge_final_heads_20251010'
down_revision: Union[str, Sequence[str], None] = (
    'c32c9ff9ca19',
    'consolidate_20250114_migrations',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Schema merge only; no-op."""
    pass


def downgrade() -> None:
    """No-op for merge revision."""
    pass
