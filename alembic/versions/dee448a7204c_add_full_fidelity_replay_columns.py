"""add_full_fidelity_replay_columns

Revision ID: dee448a7204c
Revises: 20251213_grant_permissions
Create Date: 2025-12-21 20:19:51.948999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dee448a7204c'
down_revision: Union[str, Sequence[str], None] = '20260105_fix_message_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Update job table
    op.add_column('job', sa.Column('thread_id', sa.Text(), nullable=True))
    op.create_foreign_key('fk_job_thread_id', 'job', 'thread', ['thread_id'], ['thread_id'])
    op.create_index(op.f('ix_job_thread_id'), 'job', ['thread_id'], unique=False)

    # Backfill job.thread_id from job_metadata
    op.execute("""
        UPDATE job 
        SET thread_id = (job_metadata::json->>'thread_id') 
        WHERE thread_id IS NULL 
        AND job_metadata IS NOT NULL 
        AND job_metadata != '' 
        AND job_metadata LIKE '{%'
    """)

    # 2. Update executiontracestep table
    op.add_column('executiontracestep', sa.Column('thread_id', sa.Text(), nullable=True))
    op.add_column('executiontracestep', sa.Column('message_id', sa.Text(), nullable=True))
    op.add_column('executiontracestep', sa.Column('actor', sa.Text(), nullable=True))
    op.add_column('executiontracestep', sa.Column('event_type', sa.Text(), nullable=True))
    op.add_column('executiontracestep', sa.Column('span_id', sa.Text(), nullable=True))
    op.add_column('executiontracestep', sa.Column('parent_span_id', sa.Text(), nullable=True))

    # Set defaults for existing rows
    op.execute("UPDATE executiontracestep SET actor = 'orchestrator' WHERE actor IS NULL")
    op.execute("UPDATE executiontracestep SET event_type = 'unknown' WHERE event_type IS NULL")

    # Set NOT NULL constraints
    op.alter_column('executiontracestep', 'actor', nullable=False)
    op.alter_column('executiontracestep', 'event_type', nullable=False)

    # Ensure message.message_id is unique so it can be used as a FK target
    # This might already exist if message was created by new model, but not if legacy.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='message' AND column_name='message_id'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'uq_message_message_id'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE tablename = 'message' AND indexdef LIKE '%UNIQUE%message_id%'
                ) THEN
                    ALTER TABLE public.message ADD CONSTRAINT uq_message_message_id UNIQUE (message_id);
                END IF;
            END IF;
        END$$;
    """)

    # Foreign keys
    op.create_foreign_key('fk_executiontracestep_thread_id', 'executiontracestep', 'thread', ['thread_id'], ['thread_id'])
    op.create_foreign_key('fk_executiontracestep_message_id', 'executiontracestep', 'message', ['message_id'], ['message_id'])

    # Indexes
    op.create_index(op.f('ix_executiontracestep_thread_id'), 'executiontracestep', ['thread_id'], unique=False)
    op.create_index(op.f('ix_executiontracestep_message_id'), 'executiontracestep', ['message_id'], unique=False)
    op.create_index(op.f('ix_executiontracestep_actor'), 'executiontracestep', ['actor'], unique=False)
    op.create_index(op.f('ix_executiontracestep_event_type'), 'executiontracestep', ['event_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Update executiontracestep table
    op.drop_index(op.f('ix_executiontracestep_event_type'), table_name='executiontracestep')
    op.drop_index(op.f('ix_executiontracestep_actor'), table_name='executiontracestep')
    op.drop_index(op.f('ix_executiontracestep_message_id'), table_name='executiontracestep')
    op.drop_index(op.f('ix_executiontracestep_thread_id'), table_name='executiontracestep')
    
    op.drop_constraint('fk_executiontracestep_message_id', 'executiontracestep', type_='foreignkey')
    op.drop_constraint('fk_executiontracestep_thread_id', 'executiontracestep', type_='foreignkey')

    op.drop_column('executiontracestep', 'parent_span_id')
    op.drop_column('executiontracestep', 'span_id')
    op.drop_column('executiontracestep', 'event_type')
    op.drop_column('executiontracestep', 'actor')
    op.drop_column('executiontracestep', 'message_id')
    op.drop_column('executiontracestep', 'thread_id')

    # 2. Update job table
    op.drop_index(op.f('ix_job_thread_id'), table_name='job')
    op.drop_constraint('fk_job_thread_id', 'job', type_='foreignkey')
    op.drop_column('job', 'thread_id')
