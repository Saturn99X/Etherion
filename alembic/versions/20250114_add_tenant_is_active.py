"""Shim: placeholder for legacy '20250114_add_tenant_is_active'

Revision ID: 20250114_add_tenant_is_active
Revises: merge_heads_post_20250920
Create Date: 2025-10-10 09:06:00

This migration is intentionally a no-op to satisfy legacy references.
The actual changes are applied by 'consolidate_20250114_migrations'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20250114_add_tenant_is_active'
down_revision: Union[str, Sequence[str], None] = 'merge_heads_post_20250920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op shim."""
    pass


def downgrade() -> None:
    """No-op shim."""
    pass
