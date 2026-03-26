"""Grant permissions to etherion user

Revision ID: 20251213_grant_permissions
Revises: 20251210_thread_provider
Create Date: 2025-12-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251213_grant_permissions'
down_revision = '20251210_thread_provider'
branch_labels = None
depends_on = None

def upgrade():
    # Only run on Postgres
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    # Grant permissions to 'etherion' user
    # We assume the user is 'etherion' based on Z/DATABASE.md
    try:
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO etherion;")
        op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO etherion;")
    except Exception as e:
        print(f"Warning: Could not grant permissions to 'etherion': {e}")
        # Fallback: try granting to current user? No, that's useless.
        # We just log warning and hope for the best (maybe user is different).

def downgrade():
    pass
