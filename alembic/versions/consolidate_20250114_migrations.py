"""Consolidate Jan 14 migrations to resolve overlap

Revision ID: consolidate_20250114_migrations
Revises: merge_heads_post_20250920
Replaces: 20250114_add_agent_versioning, 20250114_add_tenant_is_active_field
Create Date: 2025-10-10 08:46:50

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'consolidate_20250114_migrations'
down_revision: Union[str, Sequence[str], None] = 'merge_heads_post_20250920'
# Tell Alembic this revision replaces the overlapping ones
replaces = ('20250114_add_agent_versioning', '20250114_add_tenant_is_active_field')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Apply the net effect of both Jan 14 migrations in a single step."""
    # 1) Add is_active to tenant (from 20250114_add_tenant_is_active_field)
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.create_index('ix_tenant_is_active', 'tenant', ['is_active'])

    # 2) Add versioning fields to customagentdefinition and agentteam (from 20250114_add_agent_versioning)
    with op.batch_alter_table('customagentdefinition') as batch_op:
        batch_op.add_column(sa.Column('version', sa.String(), nullable=False, server_default='1.0.0'))
        batch_op.add_column(sa.Column('version_notes', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('parent_version', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('is_latest_version', sa.Boolean(), nullable=False, server_default='true'))
    op.create_index('ix_customagentdefinition_version', 'customagentdefinition', ['version'])
    op.create_index('ix_customagentdefinition_is_latest_version', 'customagentdefinition', ['is_latest_version'])

    with op.batch_alter_table('agentteam') as batch_op:
        batch_op.add_column(sa.Column('version', sa.String(), nullable=False, server_default='1.0.0'))
        batch_op.add_column(sa.Column('version_notes', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('parent_version', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('is_latest_version', sa.Boolean(), nullable=False, server_default='true'))
    op.create_index('ix_agentteam_version', 'agentteam', ['version'])
    op.create_index('ix_agentteam_is_latest_version', 'agentteam', ['is_latest_version'])


def downgrade() -> None:
    # Reverse versioning fields
    op.drop_index('ix_agentteam_is_latest_version', table_name='agentteam')
    op.drop_index('ix_agentteam_version', table_name='agentteam')
    with op.batch_alter_table('agentteam') as batch_op:
        batch_op.drop_column('is_latest_version')
        batch_op.drop_column('parent_version')
        batch_op.drop_column('version_notes')
        batch_op.drop_column('version')

    op.drop_index('ix_customagentdefinition_is_latest_version', table_name='customagentdefinition')
    op.drop_index('ix_customagentdefinition_version', table_name='customagentdefinition')
    with op.batch_alter_table('customagentdefinition') as batch_op:
        batch_op.drop_column('is_latest_version')
        batch_op.drop_column('parent_version')
        batch_op.drop_column('version_notes')
        batch_op.drop_column('version')

    # Reverse tenant is_active
    op.drop_index('ix_tenant_is_active', table_name='tenant')
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.drop_column('is_active')
