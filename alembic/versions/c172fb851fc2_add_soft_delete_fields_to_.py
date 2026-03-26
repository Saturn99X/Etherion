"""Add soft-delete fields to CustomAgentDefinition

Revision ID: c172fb851fc2
Revises: 9feb7d371f57
Create Date: 2025-10-11 19:05:29.167976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c172fb851fc2'
down_revision: Union[str, Sequence[str], None] = '9feb7d371f57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_deleted and deleted_at columns to customagentdefinition (SQLite-safe)."""
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table('customagentdefinition') as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_deleted',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )
        batch_op.add_column(
            sa.Column(
                'deleted_at',
                sa.DateTime(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'archived_at',
                sa.DateTime(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'is_archived',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )

    op.create_index(
        'ix_customagentdefinition_is_deleted',
        'customagentdefinition',
        ['is_deleted'],
        unique=False,
    )


def downgrade() -> None:
    """Drop is_deleted and deleted_at columns and related index."""
    op.drop_index('ix_customagentdefinition_is_deleted', table_name='customagentdefinition')
    with op.batch_alter_table('customagentdefinition') as batch_op:
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')
