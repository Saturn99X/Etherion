"""Add threads/messages/artifacts/invocations and user_settings tables

Revision ID: 20251106_add_threads_and_user_settings
Revises: 20250920_000001_add_is_system_agent_flags
Create Date: 2025-11-06 08:18:45.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '202511061000'
down_revision: Union[str, Sequence[str], None] = '20250920_000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def _has_table(name: str) -> bool:
        try:
            return insp.has_table(name)
        except Exception:
            return False

    def _has_index(table: str, index_name: str) -> bool:
        try:
            idx = [i.get('name') for i in insp.get_indexes(table)]
            return index_name in set(idx)
        except Exception:
            return False

    def _has_column(table: str, col: str) -> bool:
        try:
            cols = [c.get('name') for c in insp.get_columns(table)]
            return col in set(cols)
        except Exception:
            return False

    # threads
    if not _has_table('thread'):
        op.create_table(
            'thread',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('thread_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('team_id', sa.String(length=64), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('last_activity_at', sa.DateTime(timezone=False), nullable=True),
        )
    if _has_column('thread', 'thread_id') and not _has_index('thread', op.f('ix_thread_thread_id')):
        op.create_index(op.f('ix_thread_thread_id'), 'thread', ['thread_id'], unique=True)
    if _has_column('thread', 'tenant_id') and not _has_index('thread', op.f('ix_thread_tenant_id')):
        op.create_index(op.f('ix_thread_tenant_id'), 'thread', ['tenant_id'], unique=False)
    if _has_column('thread', 'team_id') and not _has_index('thread', op.f('ix_thread_team_id')):
        op.create_index(op.f('ix_thread_team_id'), 'thread', ['team_id'], unique=False)

    # messages
    if not _has_table('message'):
        op.create_table(
            'message',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('message_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('thread_id', sa.String(length=64), sa.ForeignKey('thread.thread_id'), nullable=False),
            sa.Column('role', sa.String(length=32), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('parent_id', sa.String(length=64), nullable=True),
            sa.Column('branch_id', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
            sa.Column('metadata_json', sa.Text(), nullable=True),
        )
    if _has_column('message', 'message_id') and not _has_index('message', op.f('ix_message_message_id')):
        op.create_index(op.f('ix_message_message_id'), 'message', ['message_id'], unique=True)
    if _has_column('message', 'thread_id') and not _has_index('message', op.f('ix_message_thread_id')):
        op.create_index(op.f('ix_message_thread_id'), 'message', ['thread_id'], unique=False)

    # message_artifacts (defer FK to conditional create)
    if not _has_table('messageartifact'):
        op.create_table(
            'messageartifact',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('message_id', sa.String(length=64), nullable=False),
            sa.Column('kind', sa.String(length=64), nullable=False),
            sa.Column('payload_ref', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        )
    if _has_column('messageartifact', 'message_id') and not _has_index('messageartifact', op.f('ix_messageartifact_message_id')):
        op.create_index(op.f('ix_messageartifact_message_id'), 'messageartifact', ['message_id'], unique=False)

    # tool_invocations (defer FK to conditional create)
    if not _has_table('toolinvocation'):
        op.create_table(
            'toolinvocation',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('invocation_id', sa.String(length=64), nullable=False, unique=True),
            sa.Column('thread_id', sa.String(length=64), sa.ForeignKey('thread.thread_id'), nullable=False),
            sa.Column('message_id', sa.String(length=64), nullable=True),
            sa.Column('tool', sa.String(length=128), nullable=False),
            sa.Column('params_json', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False),
            sa.Column('result_json', sa.Text(), nullable=True),
            sa.Column('cost', sa.Numeric(scale=6), nullable=True),
            sa.Column('timings', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        )
    if _has_column('toolinvocation', 'invocation_id') and not _has_index('toolinvocation', op.f('ix_toolinvocation_invocation_id')):
        op.create_index(op.f('ix_toolinvocation_invocation_id'), 'toolinvocation', ['invocation_id'], unique=True)
    if _has_column('toolinvocation', 'thread_id') and not _has_index('toolinvocation', op.f('ix_toolinvocation_thread_id')):
        op.create_index(op.f('ix_toolinvocation_thread_id'), 'toolinvocation', ['thread_id'], unique=False)

    # Conditionally add FKs if message.message_id exists
    if _has_table('message') and _has_column('message', 'message_id'):
        # messageartifact.message_id -> message.message_id
        existing_fks = [fk['constrained_columns'] for fk in insp.get_foreign_keys('messageartifact')] if _has_table('messageartifact') else []
        if _has_table('messageartifact') and ['message_id'] not in existing_fks:
            op.create_foreign_key(
                constraint_name=op.f('fk_messageartifact_message_id_message'),
                source_table='messageartifact',
                referent_table='message',
                local_cols=['message_id'],
                remote_cols=['message_id'],
            )
        # toolinvocation.message_id -> message.message_id
        existing_fks = [fk['constrained_columns'] for fk in insp.get_foreign_keys('toolinvocation')] if _has_table('toolinvocation') else []
        if _has_table('toolinvocation') and ['message_id'] not in existing_fks:
            op.create_foreign_key(
                constraint_name=op.f('fk_toolinvocation_message_id_message'),
                source_table='toolinvocation',
                referent_table='message',
                local_cols=['message_id'],
                remote_cols=['message_id'],
            )

    # user_settings (tenant+user scoped)
    if not _has_table('user_settings'):
        op.create_table(
            'user_settings',
            sa.Column('tenant_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('settings_json', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False),
            sa.PrimaryKeyConstraint('tenant_id', 'user_id')
        )
    if _has_column('user_settings', 'tenant_id') and not _has_index('user_settings', op.f('ix_user_settings_tenant_id')):
        op.create_index(op.f('ix_user_settings_tenant_id'), 'user_settings', ['tenant_id'], unique=False)
    if _has_column('user_settings', 'user_id') and not _has_index('user_settings', op.f('ix_user_settings_user_id')):
        op.create_index(op.f('ix_user_settings_user_id'), 'user_settings', ['user_id'], unique=False)

    # RLS policies would be added here if using PostgreSQL RLS (omitted in this migration for portability).


def downgrade() -> None:
    op.drop_table('user_settings')
    op.drop_index(op.f('ix_toolinvocation_thread_id'), table_name='toolinvocation')
    op.drop_index(op.f('ix_toolinvocation_invocation_id'), table_name='toolinvocation')
    op.drop_table('toolinvocation')
    op.drop_index(op.f('ix_messageartifact_message_id'), table_name='messageartifact')
    op.drop_table('messageartifact')
    op.drop_index(op.f('ix_message_thread_id'), table_name='message')
    op.drop_index(op.f('ix_message_message_id'), table_name='message')
    op.drop_table('message')
    op.drop_index(op.f('ix_thread_team_id'), table_name='thread')
    op.drop_index(op.f('ix_thread_tenant_id'), table_name='thread')
    op.drop_index(op.f('ix_thread_thread_id'), table_name='thread')
    op.drop_table('thread')
