"""Merge migration heads

Revision ID: ed067a43fe61
Revises: 9025eb395671, def456ghi789
Create Date: 2025-08-31 11:01:41.477372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed067a43fe61'
down_revision: Union[str, Sequence[str], None] = ('9025eb395671', 'def456ghi789')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
