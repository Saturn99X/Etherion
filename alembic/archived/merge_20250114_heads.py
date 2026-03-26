"""Merge heads for Jan 14 revisions

Revision ID: merge_20250114_heads
Revises: 20250114_add_agent_versioning, 20250114_add_tenant_is_active_field
Create Date: 2025-10-10 08:36:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'merge_20250114_heads'
down_revision: Union[str, Sequence[str], None] = '20250114_add_agent_versioning'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Schema merge only; no-op."""
    pass


def downgrade() -> None:
    """No-op for merge revision."""
    pass
