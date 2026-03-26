"""add_foreign_key_constraints_and_indexes

Revision ID: 9b2e6833c9ea
Revises: 20250114_add_agent_versioning
Create Date: 2025-09-20 11:23:59.397030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '9b2e6833c9ea'
down_revision: Union[str, Sequence[str], None] = 'consolidate_20250114_migrations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add foreign key constraints and indexes for better data integrity and performance."""

    bind = op.get_bind()

    def constraint_exists(name: str) -> bool:
        result = bind.execute(text("SELECT 1 FROM pg_constraint WHERE conname = :name"), {"name": name})
        return result.scalar() is not None

    def index_exists(name: str) -> bool:
        result = bind.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = :name"
            ),
            {"name": name},
        )
        return result.scalar() is not None

    # Add foreign key constraints for Job table
    if not constraint_exists('fk_job_tenant_id'):
        with op.batch_alter_table('job', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_job_tenant_id', 'tenant', ['tenant_id'], ['id'])
    if not constraint_exists('fk_job_user_id'):
        with op.batch_alter_table('job', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_job_user_id', 'user', ['user_id'], ['id'])

    # Add foreign key constraints for ExecutionTraceStep table
    if not constraint_exists('fk_executiontracestep_tenant_id'):
        with op.batch_alter_table('executiontracestep', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_executiontracestep_tenant_id', 'tenant', ['tenant_id'], ['id'])

    # Add foreign key constraints for CustomAgentDefinition table
    if not constraint_exists('fk_customagentdefinition_tenant_id'):
        with op.batch_alter_table('customagentdefinition', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_customagentdefinition_tenant_id', 'tenant', ['tenant_id'], ['id'])

    # Add foreign key constraints for AgentTeam table
    if not constraint_exists('fk_agentteam_tenant_id'):
        with op.batch_alter_table('agentteam', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_agentteam_tenant_id', 'tenant', ['tenant_id'], ['id'])

    # Add composite indexes for frequently queried combinations
    if not index_exists('ix_job_tenant_status'):
        op.create_index('ix_job_tenant_status', 'job', ['tenant_id', 'status'])

    if not index_exists('ix_job_tenant_created'):
        op.create_index('ix_job_tenant_created', 'job', ['tenant_id', 'created_at'])

    if not index_exists('ix_executiontracestep_tenant_job'):
        op.create_index('ix_executiontracestep_tenant_job', 'executiontracestep', ['tenant_id', 'job_id'])

    if not index_exists('ix_executiontracestep_tenant_timestamp'):
        op.create_index('ix_executiontracestep_tenant_timestamp', 'executiontracestep', ['tenant_id', 'timestamp'])

    if not index_exists('ix_customagentdefinition_tenant_active'):
        op.create_index('ix_customagentdefinition_tenant_active', 'customagentdefinition', ['tenant_id', 'is_active'])

    if not index_exists('ix_agentteam_tenant_active'):
        op.create_index('ix_agentteam_tenant_active', 'agentteam', ['tenant_id', 'is_active'])

    # Add indexes for foreign key columns that don't have them yet
    if not index_exists('ix_project_user_id'):
        op.create_index('ix_project_user_id', 'project', ['user_id'])

    if not index_exists('ix_project_tenant_id'):
        op.create_index('ix_project_tenant_id', 'project', ['tenant_id'])

    if not index_exists('ix_toneprofile_user_id'):
        op.create_index('ix_toneprofile_user_id', 'toneprofile', ['user_id'])

    if not index_exists('ix_toneprofile_tenant_id'):
        op.create_index('ix_toneprofile_tenant_id', 'toneprofile', ['tenant_id'])

    if not index_exists('ix_conversation_project_id'):
        op.create_index('ix_conversation_project_id', 'conversation', ['project_id'])

    if not index_exists('ix_conversation_tenant_id'):
        op.create_index('ix_conversation_tenant_id', 'conversation', ['tenant_id'])

    if not index_exists('ix_projectkbfile_project_id'):
        op.create_index('ix_projectkbfile_project_id', 'projectkbfile', ['project_id'])

    if not index_exists('ix_projectkbfile_tenant_id'):
        op.create_index('ix_projectkbfile_tenant_id', 'projectkbfile', ['tenant_id'])

    if not index_exists('ix_message_conversation_id'):
        op.create_index('ix_message_conversation_id', 'message', ['conversation_id'])

    if not index_exists('ix_message_tenant_id'):
        op.create_index('ix_message_tenant_id', 'message', ['tenant_id'])

    if not index_exists('ix_expense_user_id'):
        op.create_index('ix_expense_user_id', 'expense', ['user_id'])

    if not index_exists('ix_expense_tenant_id'):
        op.create_index('ix_expense_tenant_id', 'expense', ['tenant_id'])

    if not index_exists('ix_executioncost_tenant_id'):
        op.create_index('ix_executioncost_tenant_id', 'executioncost', ['tenant_id'])


def downgrade() -> None:
    """Remove foreign key constraints and indexes."""
    
    # Drop composite indexes
    try:
        op.drop_index('ix_executioncost_tenant_id', table_name='executioncost')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_expense_tenant_id', table_name='expense')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_expense_user_id', table_name='expense')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_message_tenant_id', table_name='message')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_message_conversation_id', table_name='message')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_projectkbfile_tenant_id', table_name='projectkbfile')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_projectkbfile_project_id', table_name='projectkbfile')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_conversation_tenant_id', table_name='conversation')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_conversation_project_id', table_name='conversation')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_toneprofile_tenant_id', table_name='toneprofile')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_toneprofile_user_id', table_name='toneprofile')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_project_tenant_id', table_name='project')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_project_user_id', table_name='project')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_agentteam_tenant_active', table_name='agentteam')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_customagentdefinition_tenant_active', table_name='customagentdefinition')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_executiontracestep_tenant_timestamp', table_name='executiontracestep')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_executiontracestep_tenant_job', table_name='executiontracestep')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_job_tenant_created', table_name='job')
    except Exception:
        pass  # Index doesn't exist
    
    try:
        op.drop_index('ix_job_tenant_status', table_name='job')
    except Exception:
        pass  # Index doesn't exist
    
    # Drop foreign key constraints
    try:
        with op.batch_alter_table('agentteam', schema=None) as batch_op:
            batch_op.drop_constraint('fk_agentteam_tenant_id', type_='foreignkey')
    except Exception:
        pass  # Constraint doesn't exist
    
    try:
        with op.batch_alter_table('customagentdefinition', schema=None) as batch_op:
            batch_op.drop_constraint('fk_customagentdefinition_tenant_id', type_='foreignkey')
    except Exception:
        pass  # Constraint doesn't exist
    
    try:
        with op.batch_alter_table('executiontracestep', schema=None) as batch_op:
            batch_op.drop_constraint('fk_executiontracestep_tenant_id', type_='foreignkey')
    except Exception:
        pass  # Constraint doesn't exist
    
    try:
        with op.batch_alter_table('job', schema=None) as batch_op:
            batch_op.drop_constraint('fk_job_user_id', type_='foreignkey')
            batch_op.drop_constraint('fk_job_tenant_id', type_='foreignkey')
    except Exception:
        pass  # Constraints don't exist
