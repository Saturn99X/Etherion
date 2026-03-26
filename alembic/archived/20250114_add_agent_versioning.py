"""Add agent versioning fields

Revision ID: 20250114_add_agent_versioning
Revises: 20250114_add_tenant_is_active_field
Create Date: 2025-01-14 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250114_add_agent_versioning'
down_revision: Union[str, None] = '20250114_add_tenant_is_active_field'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add versioning fields to agent tables."""
    
    # Add versioning fields to customagentdefinition table
    op.add_column('customagentdefinition', sa.Column('version', sa.String(), nullable=False, server_default='1.0.0'))
    op.add_column('customagentdefinition', sa.Column('version_notes', sa.String(), nullable=True))
    op.add_column('customagentdefinition', sa.Column('parent_version', sa.String(), nullable=True))
    op.add_column('customagentdefinition', sa.Column('is_latest_version', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add indexes for versioning fields
    op.create_index('ix_customagentdefinition_version', 'customagentdefinition', ['version'])
    op.create_index('ix_customagentdefinition_is_latest_version', 'customagentdefinition', ['is_latest_version'])
    
    # Add versioning fields to agentteam table
    op.add_column('agentteam', sa.Column('version', sa.String(), nullable=False, server_default='1.0.0'))
    op.add_column('agentteam', sa.Column('version_notes', sa.String(), nullable=True))
    op.add_column('agentteam', sa.Column('parent_version', sa.String(), nullable=True))
    op.add_column('agentteam', sa.Column('is_latest_version', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add indexes for versioning fields
    op.create_index('ix_agentteam_version', 'agentteam', ['version'])
    op.create_index('ix_agentteam_is_latest_version', 'agentteam', ['is_latest_version'])


def downgrade() -> None:
    """Remove versioning fields from agent tables."""
    
    # Remove indexes
    op.drop_index('ix_agentteam_is_latest_version', table_name='agentteam')
    op.drop_index('ix_agentteam_version', table_name='agentteam')
    op.drop_index('ix_customagentdefinition_is_latest_version', table_name='customagentdefinition')
    op.drop_index('ix_customagentdefinition_version', table_name='customagentdefinition')
    
    # Remove columns from agentteam table
    op.drop_column('agentteam', 'is_latest_version')
    op.drop_column('agentteam', 'parent_version')
    op.drop_column('agentteam', 'version_notes')
    op.drop_column('agentteam', 'version')
    
    # Remove columns from customagentdefinition table
    op.drop_column('customagentdefinition', 'is_latest_version')
    op.drop_column('customagentdefinition', 'parent_version')
    op.drop_column('customagentdefinition', 'version_notes')
    op.drop_column('customagentdefinition', 'version')
