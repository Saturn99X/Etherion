"""populate_tenant_data_and_tenant_id_fields_non_nullable

Revision ID: 345fe61a61c6
Revises: e8e79e727330
Create Date: 2025-08-21 16:41:02.239225

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import Table, MetaData
from datetime import datetime


# revision identifiers, used by Alembic.
revision: str = '345fe61a61c6'
down_revision: Union[str, Sequence[str], None] = 'e8e79e727330'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Get the database connection
    connection = op.get_bind()
    meta = MetaData()
    meta.reflect(bind=connection)
    
    # Get tables
    tenant_table = meta.tables['tenant']
    user_table = meta.tables['user']
    project_table = meta.tables['project']
    conversation_table = meta.tables['conversation']
    projectkbfile_table = meta.tables['projectkbfile']
    toneprofile_table = meta.tables['toneprofile']
    message_table = meta.tables['message']
    
    # Create a default tenant for existing data
    import secrets
    import string
    
    def generate_unique_id(length: int = 13) -> str:
        """Generate a unique URL-safe identifier."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    default_tenant_id_str = generate_unique_id()
    
    connection.execute(
        tenant_table.insert().values(
            tenant_id=default_tenant_id_str,
            subdomain="default",
            name="Default Tenant",
            admin_email="admin@localhost",
            created_at=datetime.utcnow()
        )
    )
    
    # Get the default tenant ID
    result = connection.execute(
        sa.select(tenant_table.c.id).where(tenant_table.c.subdomain == "default")
    )
    default_tenant_id = result.fetchone()[0]
    
    # Update all existing records with the default tenant ID
    connection.execute(
        user_table.update().values(
            tenant_id=default_tenant_id,
            provider="google"  # Set default provider
        )
    )
    
    connection.execute(
        project_table.update().values(tenant_id=default_tenant_id)
    )
    
    connection.execute(
        conversation_table.update().values(tenant_id=default_tenant_id)
    )
    
    connection.execute(
        projectkbfile_table.update().values(tenant_id=default_tenant_id)
    )
    
    connection.execute(
        toneprofile_table.update().values(tenant_id=default_tenant_id)
    )
    
    connection.execute(
        message_table.update().values(tenant_id=default_tenant_id)
    )
    
    # Now make the tenant_id fields non-nullable
    # Note: This is a simplified approach. In a real production environment,
    # you would need more sophisticated handling of existing data.
    
    # Make tenant_id non-nullable for all tables using batch mode for SQLite
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
    
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
    
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
    
    with op.batch_alter_table('projectkbfile', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
    
    with op.batch_alter_table('toneprofile', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
    
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=False)
        batch_op.alter_column('provider', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Make tenant_id fields nullable again
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=True)
        batch_op.alter_column('provider', nullable=True)
    
    with op.batch_alter_table('toneprofile', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=True)
    
    with op.batch_alter_table('projectkbfile', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=True)
    
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=True)
    
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=True)
    
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', nullable=True)
    
    # Remove the default tenant
    connection = op.get_bind()
    meta = MetaData()
    meta.reflect(bind=connection)
    tenant_table = meta.tables['tenant']
    
    connection.execute(
        tenant_table.delete().where(tenant_table.c.subdomain == "default")
    )
