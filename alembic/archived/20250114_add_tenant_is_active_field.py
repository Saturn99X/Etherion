"""Add is_active field to tenant table

Revision ID: 20250114_add_tenant_is_active_field
Revises: merge_heads_post_20250920
Create Date: 2025-01-14 12:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250114_add_tenant_is_active_field'
down_revision = 'merge_heads_post_20250920'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_active field to tenant table
    op.add_column('tenant', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add index for performance
    op.create_index('ix_tenant_is_active', 'tenant', ['is_active'])


def downgrade():
    # Remove index
    op.drop_index('ix_tenant_is_active', table_name='tenant')
    
    # Remove is_active field
    op.drop_column('tenant', 'is_active')
