"""create ip_address_usage table

Revision ID: a3ef8a577476
Revises: 20251018_merge_rls_retention_heads
Create Date: 2025-10-18 18:20:03.945463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3ef8a577476'
down_revision: Union[str, Sequence[str], None] = '202510181200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ip_address_usage table."""
    op.create_table(
        'ip_address_usage',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('ip_hash', sa.String(length=128), nullable=False),
        sa.Column('purpose', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('blocked_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
    )
    op.create_index('ix_ip_address_usage_ip_hash', 'ip_address_usage', ['ip_hash'])
    op.create_index('ix_ip_address_usage_purpose', 'ip_address_usage', ['purpose'])
    op.create_index('ix_ip_address_usage_tenant_id', 'ip_address_usage', ['tenant_id'])
    op.create_index('ix_ip_address_usage_user_id', 'ip_address_usage', ['user_id'])


def downgrade() -> None:
    """Drop ip_address_usage table."""
    op.drop_index('ix_ip_address_usage_user_id', table_name='ip_address_usage')
    op.drop_index('ix_ip_address_usage_tenant_id', table_name='ip_address_usage')
    op.drop_index('ix_ip_address_usage_purpose', table_name='ip_address_usage')
    op.drop_index('ix_ip_address_usage_ip_hash', table_name='ip_address_usage')
    op.drop_table('ip_address_usage')
