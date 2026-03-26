"""Add checklist and checklist_item tables.

Revision ID: 20260316_add_checklist
Revises: 20260115_secure_cred
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = '20260316_add_checklist'
down_revision = '20260115_secure_cred'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'checklist',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('checklist_id', sa.String, nullable=False),
        sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_complete', sa.Boolean, server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_checklist_checklist_id', 'checklist', ['checklist_id'], unique=True)
    op.create_index('ix_checklist_tenant_id', 'checklist', ['tenant_id'])

    op.create_table(
        'checklistitem',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('checklist_id', sa.Integer, sa.ForeignKey('checklist.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', sa.Integer, nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('is_checked', sa.Boolean, server_default='false', nullable=False),
        sa.Column('order', sa.Integer, server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_checklistitem_checklist_id', 'checklistitem', ['checklist_id'])
    op.create_index('ix_checklistitem_tenant_id', 'checklistitem', ['tenant_id'])

    # Enable Row Level Security
    op.execute("ALTER TABLE checklist ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE checklistitem ENABLE ROW LEVEL SECURITY")

    # RLS policies (tenant isolation via SET app.tenant_id)
    op.execute("""
        CREATE POLICY checklist_tenant_isolation ON checklist
        USING (tenant_id = current_setting('app.tenant_id', true)::integer)
    """)
    op.execute("""
        CREATE POLICY checklistitem_tenant_isolation ON checklistitem
        USING (tenant_id = current_setting('app.tenant_id', true)::integer)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS checklistitem_tenant_isolation ON checklistitem")
    op.execute("DROP POLICY IF EXISTS checklist_tenant_isolation ON checklist")
    op.drop_table('checklistitem')
    op.drop_table('checklist')
