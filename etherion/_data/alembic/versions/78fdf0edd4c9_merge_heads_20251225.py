"""merge_heads_20251225

Revision ID: 78fdf0edd4c9
Revises: 20251225_mmkb, dee448a7204c
Create Date: 2025-12-25 02:56:53.189100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78fdf0edd4c9'
down_revision: Union[str, Sequence[str], None] = ('20251225_mmkb', 'dee448a7204c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
