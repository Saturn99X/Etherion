"""Add SecureCredential table for encrypted credential storage

Revision ID: 20260115_secure_cred
Revises: 78fdf0edd4c9
Create Date: 2026-01-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260115_secure_cred'
down_revision = '78fdf0edd4c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create SecureCredential table
    op.create_table(
        'securecredential',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('service_name', sa.String(), nullable=False),
        sa.Column('environment', sa.String(), nullable=False, server_default='production'),
        sa.Column('credential_type', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
        sa.Column('encrypted_data', sa.Text(), nullable=False),
        sa.Column('encryption_key_id', sa.String(), nullable=False),
        sa.Column('checksum', sa.String(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('last_updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('access_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_accessed_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_securecredential_tenant_id', 'securecredential', ['tenant_id'])
    op.create_index('ix_securecredential_user_id', 'securecredential', ['user_id'])
    op.create_index('ix_securecredential_tool_name', 'securecredential', ['tool_name'])
    op.create_index('ix_securecredential_service_name', 'securecredential', ['service_name'])
    op.create_index('ix_securecredential_environment', 'securecredential', ['environment'])
    op.create_index('ix_securecredential_status', 'securecredential', ['status'])
    op.create_index('ix_securecredential_created_at', 'securecredential', ['created_at'])
    op.create_index('ix_securecredential_last_used_at', 'securecredential', ['last_used_at'])
    
    # Create composite index for common queries
    op.create_index(
        'ix_securecredential_tenant_tool_service',
        'securecredential',
        ['tenant_id', 'tool_name', 'service_name']
    )
    
    # Enable RLS on the table
    op.execute('ALTER TABLE securecredential ENABLE ROW LEVEL SECURITY')
    
    # Create RLS policy for tenant isolation
    op.execute('''
        CREATE POLICY securecredential_tenant_isolation ON securecredential
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant_id', true)::integer)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::integer)
    ''')


def downgrade() -> None:
    # Drop RLS policy
    op.execute('DROP POLICY IF EXISTS securecredential_tenant_isolation ON securecredential')
    
    # Disable RLS
    op.execute('ALTER TABLE securecredential DISABLE ROW LEVEL SECURITY')
    
    # Drop indexes
    op.drop_index('ix_securecredential_tenant_tool_service', table_name='securecredential')
    op.drop_index('ix_securecredential_last_used_at', table_name='securecredential')
    op.drop_index('ix_securecredential_created_at', table_name='securecredential')
    op.drop_index('ix_securecredential_status', table_name='securecredential')
    op.drop_index('ix_securecredential_environment', table_name='securecredential')
    op.drop_index('ix_securecredential_service_name', table_name='securecredential')
    op.drop_index('ix_securecredential_tool_name', table_name='securecredential')
    op.drop_index('ix_securecredential_user_id', table_name='securecredential')
    op.drop_index('ix_securecredential_tenant_id', table_name='securecredential')
    
    # Drop table
    op.drop_table('securecredential')
