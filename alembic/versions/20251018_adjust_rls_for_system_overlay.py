"""
Adjust RLS policies for system overlay visibility on customagentdefinition and agentteam.

Revision ID: 20251018_adjust_rls_for_system_overlay
Revises: merge_final_heads_20251010
Create Date: 2025-10-18 09:22:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '202510181000'
down_revision: Union[str, Sequence[str], None] = 'merge_final_heads_20251010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    # Ensure RLS is enabled
    op.execute("ALTER TABLE customagentdefinition ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE agentteam ENABLE ROW LEVEL SECURITY;")

    # Add a SELECT policy to allow reading global 'system' rows for all tenants.
    # This complements the existing tenant equality policy.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = current_schema()
                  AND tablename = 'customagentdefinition'
                  AND policyname = 'system_read_cad'
            ) THEN
                CREATE POLICY system_read_cad ON customagentdefinition
                  FOR SELECT
                  USING (is_system_agent = true);
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = current_schema()
                  AND tablename = 'agentteam'
                  AND policyname = 'system_read_at'
            ) THEN
                CREATE POLICY system_read_at ON agentteam
                  FOR SELECT
                  USING (is_system_agent = true);
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.execute("DROP POLICY IF EXISTS system_read_cad ON customagentdefinition;")
    op.execute("DROP POLICY IF EXISTS system_read_at ON agentteam;")
