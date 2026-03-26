"""Remove billing tables (expense, executioncost, credit_ledger).

Revision ID: 20260316_remove_billing
Revises: 20260316_add_checklist
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '20260316_remove_billing'
down_revision = '20260316_add_checklist'
branch_labels = None
depends_on = None

_BILLING_TABLES = ['expense', 'executioncost', 'credit_ledger']


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    for table in _BILLING_TABLES:
        if _table_exists(table):
            # Drop RLS policies first
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            op.drop_table(table)


def downgrade() -> None:
    # Recreate expense table
    if not _table_exists('expense'):
        op.create_table(
            'expense',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.Integer, nullable=False),
            sa.Column('amount', sa.Numeric(10, 4), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )

    # Recreate executioncost table
    if not _table_exists('executioncost'):
        op.create_table(
            'executioncost',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.Integer, nullable=False),
            sa.Column('job_id', sa.String, nullable=True),
            sa.Column('model', sa.String, nullable=True),
            sa.Column('input_tokens', sa.Integer, server_default='0'),
            sa.Column('output_tokens', sa.Integer, server_default='0'),
            sa.Column('cost_usd', sa.Numeric(10, 6), server_default='0'),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )

    # Recreate credit_ledger table
    if not _table_exists('credit_ledger'):
        op.create_table(
            'credit_ledger',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.Integer, nullable=False),
            sa.Column('credits_delta', sa.Integer, nullable=False),
            sa.Column('reason', sa.String, nullable=True),
            sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        )
