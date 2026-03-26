"""Enable RLS and create tenant isolation policies

Revision ID: 20250913_enable_rls_policies
Revises: [previous_revision_hash, e.g., f8c9d7d2a4e1]
Create Date: 2025-09-13 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250913_enable_rls_policies'
down_revision = '202509121058'
branch_labels = None
depends_on = None

tenant_aware_tables = [
    'tenant', 'user', 'project', 'toneprofile', 'conversation', 
    'projectkbfile', 'message', 'expense', 'executioncost', 'job',
    'customagentdefinition', 'agentteam', 'scheduledtask', 'executiontracestep'
]

def upgrade():
    # Guard: Only execute on PostgreSQL. SQLite (dev) does not support RLS.
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    # Enable RLS on each tenant-aware table
    for table in tenant_aware_tables:
        quoted_table = f'"{table}"'
        op.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY;")

        policy_column = "id" if table == "tenant" else "tenant_id"
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {quoted_table}
            USING ({policy_column} = current_setting('app.tenant_id')::integer)
            WITH CHECK ({policy_column} = current_setting('app.tenant_id')::integer);
            """
        )

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    for table in tenant_aware_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table} FOR ALL;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
