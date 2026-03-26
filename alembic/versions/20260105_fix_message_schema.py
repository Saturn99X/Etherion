"""fix_message_schema

Revision ID: 20260105_fix_message_schema
Revises: 20251213_grant_permissions
Create Date: 2026-01-05 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '20260105_fix_message_schema'
down_revision: Union[str, Sequence[str], None] = '20251213_grant_permissions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('message')]
    column_set = set(columns)

    # 1. Add missing columns to 'message' table
    if 'message_id' not in column_set:
        op.add_column('message', sa.Column('message_id', sa.String(length=64), nullable=True))
    
    if 'thread_id' not in column_set:
        op.add_column('message', sa.Column('thread_id', sa.String(length=64), nullable=True))
    
    if 'parent_id' not in column_set:
        op.add_column('message', sa.Column('parent_id', sa.String(length=64), nullable=True))
    
    if 'branch_id' not in column_set:
        op.add_column('message', sa.Column('branch_id', sa.String(length=64), nullable=True))
    
    if 'metadata_json' not in column_set:
        op.add_column('message', sa.Column('metadata_json', sa.Text(), nullable=True))

    # 2. Backfill message_id and thread_id for existing rows if they are null
    # We use 'm-' + id for message_id backfill
    conn.execute(sa.text("UPDATE message SET message_id = 'm-' || id::text WHERE message_id IS NULL"))
    
    # thread_id is harder to backfill if we don't have a direct mapping, 
    # but for a fresh migration in the new project there shouldn't be data yet.
    # If there is data, we'll need to handle it or allow nulls temporarily.

    # 3. Apply NOT NULL and Unique constraints
    # op.alter_column('message', 'message_id', nullable=False)
    # op.create_unique_constraint('uq_message_message_id', 'message', ['message_id'])

    # 4. Add foreign keys if they don't exist
    fks = inspector.get_foreign_keys('message')
    fk_names = set(fk['name'] for fk in fks)
    
    if 'fk_message_thread_id' not in fk_names:
        op.create_foreign_key(
            'fk_message_thread_id', 'message', 'thread',
            ['thread_id'], ['thread_id']
        )

    # 5. Create index on message_id if it doesn't exist
    indices = inspector.get_indexes('message')
    index_names = set(idx['name'] for idx in indices)
    if 'ix_message_message_id' not in index_names:
        op.create_index('ix_message_message_id', 'message', ['message_id'], unique=True)

def downgrade() -> None:
    pass
