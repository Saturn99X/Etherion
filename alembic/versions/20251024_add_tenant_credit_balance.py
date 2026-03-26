"""
Create tenant_credit_balance table with RLS

Revision ID: 20251024_add_tenant_credit_balance
Revises: 20251024_add_credit_ledger_and_stripe_event
Create Date: 2025-10-24 08:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "202510241200"
down_revision: Union[str, Sequence[str], None] = "202510241000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_credit_balance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("balance_credits", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index(
        "ux_tenant_credit_balance_tenant_user",
        "tenant_credit_balance",
        ["tenant_id", "user_id"],
        unique=True,
    )

    # Enable RLS on Postgres
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE tenant_credit_balance ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation ON tenant_credit_balance
            USING (tenant_id = current_setting('app.tenant_id')::integer)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::integer);
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_credit_balance;")
        op.execute("ALTER TABLE tenant_credit_balance DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ux_tenant_credit_balance_tenant_user", table_name="tenant_credit_balance")
    op.drop_table("tenant_credit_balance")
