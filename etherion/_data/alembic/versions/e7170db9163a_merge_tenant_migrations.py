"""merge_tenant_migrations

Revision ID: e7170db9163a
Revises: bf44d6c011e9, 345fe61a61c6
Create Date: 2025-08-22 09:06:44.668107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7170db9163a'
down_revision: Union[str, Sequence[str], None] = ('bf44d6c011e9', '345fe61a61c6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
