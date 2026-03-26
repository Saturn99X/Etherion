"""
Add is_system_agent flags to CustomAgentDefinition and AgentTeam

Revision ID: 20250920_000001
Revises: 20250913_enable_rls_policies
Create Date: 2025-09-20 00:00:01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250920_000001'
down_revision: Union[str, Sequence[str], None] = '20250913_enable_rls_policies'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customagentdefinition', sa.Column('is_system_agent', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index(op.f('ix_customagentdefinition_is_system_agent'), 'customagentdefinition', ['is_system_agent'], unique=False)

    op.add_column('agentteam', sa.Column('is_system_agent', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index(op.f('ix_agentteam_is_system_agent'), 'agentteam', ['is_system_agent'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agentteam_is_system_agent'), table_name='agentteam')
    op.drop_column('agentteam', 'is_system_agent')
    op.drop_index(op.f('ix_customagentdefinition_is_system_agent'), table_name='customagentdefinition')
    op.drop_column('customagentdefinition', 'is_system_agent')


