"""Unify all heads into a single head

Revision ID: 9feb7d371f57
Revises: 20250114_add_agent_versioning, 20250114_add_tenant_is_active, merge_final_heads_20251010
Create Date: 2025-10-10 21:23:02.375880

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9feb7d371f57'
down_revision: Union[str, Sequence[str], None] = ('20250114_add_agent_versioning', '20250114_add_tenant_is_active', 'merge_final_heads_20251010')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
