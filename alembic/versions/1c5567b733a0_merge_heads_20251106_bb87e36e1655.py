"""merge heads 20251106 + bb87e36e1655

Revision ID: 1c5567b733a0
Revises: 20251106_add_threads_and_user_settings, bb87e36e1655
Create Date: 2025-11-06 08:54:41.121076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c5567b733a0'
down_revision: Union[str, Sequence[str], None] = ('202511061000', 'bb87e36e1655')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
