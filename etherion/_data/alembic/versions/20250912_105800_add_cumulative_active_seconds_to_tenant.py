"""Add cumulative_active_seconds to Tenant

Revision ID: add_cumulative_active_seconds_to_tenant
Revises: [previous_revision_id]  # Replace with actual previous, e.g., 20250904_102830_refactor_job_data_persistence
Create Date: 2025-09-12 10:58

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.


revision = '202509121058'
down_revision = 'f4b599b897f2'
branch_labels = None
depends_on = None



def upgrade() -> None:
    # Add column to Tenant table
    op.add_column('tenant', sa.Column(
        'cumulative_active_seconds', sa.Float(), nullable=False, server_default='0.0', index=True
    ))

    # Backfill existing tenants
    op.execute("UPDATE tenant SET cumulative_active_seconds = 0.0 WHERE cumulative_active_seconds IS NULL")


def downgrade() -> None:
    # Remove column from Tenant table
    op.drop_column('tenant', 'cumulative_active_seconds')
