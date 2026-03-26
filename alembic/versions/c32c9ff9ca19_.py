"""empty message

Revision ID: c32c9ff9ca19
Revises: 20250115_add_user_observation_table, 9b2e6833c9ea
Create Date: 2025-09-23 18:25:48.268427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c32c9ff9ca19'
down_revision: Union[str, Sequence[str], None] = ('202501151000', '9b2e6833c9ea')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
