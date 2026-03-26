"""
Add credit_ledger and stripe_event tables; enable RLS for credit_ledger on Postgres

Revision ID: 20251024_add_credit_ledger_and_stripe_event
Revises: 20251018_merge_rls_retention_heads
Create Date: 2025-10-24 07:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "202510241000"
down_revision: Union[str, Sequence[str], None] = "202510181200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # credit_ledger
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),  # DEDUCTION|PAYMENT|REFUND|FREE_GRANT|ADJUSTMENT
        sa.Column("credits_delta", sa.Integer(), nullable=False),
        sa.Column("usd_amount", sa.Numeric(12, 6), nullable=True),
        sa.Column("payment_reference", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_credit_ledger_tenant_id_created_at", "credit_ledger", ["tenant_id", "created_at"], unique=False)

    # stripe_event idempotency store
    op.create_table(
        "stripe_event",
        sa.Column("event_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    # Enable RLS on Postgres for credit_ledger
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation ON credit_ledger
            USING (tenant_id = current_setting('app.tenant_id')::integer)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::integer);
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON credit_ledger;")
        op.execute("ALTER TABLE credit_ledger DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_credit_ledger_tenant_id_created_at", table_name="credit_ledger")
    op.drop_table("credit_ledger")

    op.drop_table("stripe_event")
