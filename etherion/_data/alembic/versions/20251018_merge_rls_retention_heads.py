"""
Merge heads after RLS overlay and retention policy migrations.

Revision ID: 20251018_merge_rls_retention_heads
Revises: 20251018_adjust_rls_for_system_overlay, dc8b9721e09c
Create Date: 2025-10-18 17:59:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "202510181200"
down_revision: Union[str, Sequence[str], None] = (
    "202510181000",
    "dc8b9721e09c",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
