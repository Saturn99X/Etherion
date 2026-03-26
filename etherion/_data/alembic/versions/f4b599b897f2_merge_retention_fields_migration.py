"""merge retention fields migration

Revision ID: f4b599b897f2
Revises: 20250904_102830, 65c893f3540a
Create Date: 2025-09-08 14:31:30.573752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4b599b897f2'
down_revision: Union[str, Sequence[str], None] = '20250904_102830'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
