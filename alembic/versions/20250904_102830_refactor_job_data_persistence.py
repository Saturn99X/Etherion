"""
Refactor Job table for GCS-based data persistence.

This migration removes the output_data field and adds GCS URI fields for
trace and output data storage, implementing the "Cold Storage" workflow.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250904_102830'
# This migration refactors the Job table and must run after tools and job enhancements
# in 65c893f3540a (adds Tool/CustomAgentDefinition/AgentTeam and job.expires_at).
down_revision = '65c893f3540a'
branch_labels = None
depends_on = None

def upgrade():
    """Apply the database schema changes for GCS-based persistence."""

    # Add new GCS URI columns
    op.add_column('job', sa.Column('trace_data_uri', sa.String(2048), nullable=True))
    op.add_column('job', sa.Column('output_data_uri', sa.String(2048), nullable=True))

    # Create indexes for the new URI columns for better query performance
    op.create_index('ix_job_trace_data_uri', 'job', ['trace_data_uri'])
    op.create_index('ix_job_output_data_uri', 'job', ['output_data_uri'])

    # Note: We're keeping the output_data column for now to allow for gradual migration
    # It will be removed in a future migration after confirming all data has been migrated to GCS

    # Add comments to document the new columns (SQLite compatible)
    if op.get_bind().dialect.name != 'sqlite':
        op.execute("""
            COMMENT ON COLUMN job.trace_data_uri IS 'GCS URI pointing to the job execution trace file (JSONL format)'
        """)

        op.execute("""
            COMMENT ON COLUMN job.output_data_uri IS 'GCS URI pointing to the job output file (text format)'
        """)

def downgrade():
    """Revert the database schema changes."""

    # Remove the indexes first
    op.drop_index('ix_job_output_data_uri', table_name='job')
    op.drop_index('ix_job_trace_data_uri', table_name='job')

    # Remove the new columns
    op.drop_column('job', 'output_data_uri')
    op.drop_column('job', 'trace_data_uri')
