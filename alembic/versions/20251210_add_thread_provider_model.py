"""Add provider/model columns to thread table for per-thread LLM preferences

Revision ID: 20251210_thread_provider
Revises: 1c5567b733a0
Create Date: 2025-12-10 09:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251210_thread_provider"
down_revision: Union[str, Sequence[str], None] = "1c5567b733a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add provider/model/tone_profile_id columns to thread."""
    with op.batch_alter_table("thread") as batch_op:
        batch_op.add_column(sa.Column("provider", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("tone_profile_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema: drop provider/model/tone_profile_id columns from thread."""
    with op.batch_alter_table("thread") as batch_op:
        batch_op.drop_column("tone_profile_id")
        batch_op.drop_column("model")
        batch_op.drop_column("provider")
