"""merge_heads_20251024

Revision ID: bb87e36e1655
Revises: 20251024_add_tenant_credit_balance, a3ef8a577476
Create Date: 2025-10-24 10:43:38.902865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb87e36e1655'
down_revision: Union[str, Sequence[str], None] = ('202510241200', 'a3ef8a577476')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
