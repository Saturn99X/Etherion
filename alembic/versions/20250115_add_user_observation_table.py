"""Add user_observation table for user personality tracking

Revision ID: 20250115_add_user_observation_table
Revises: merge_heads_post_20250920
Create Date: 2025-01-15 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '202501151000'
down_revision: Union[str, Sequence[str], None] = 'merge_heads_post_20250920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('userobservation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('preferred_tone', sa.String(), nullable=False),
    sa.Column('response_length_preference', sa.String(), nullable=False),
    sa.Column('technical_level', sa.String(), nullable=False),
    sa.Column('formality_level', sa.String(), nullable=False),
    sa.Column('patience_level', sa.String(), nullable=False),
    sa.Column('detail_orientation', sa.String(), nullable=False),
    sa.Column('risk_tolerance', sa.String(), nullable=False),
    sa.Column('decision_making_style', sa.String(), nullable=False),
    sa.Column('successful_tools', sa.String(), nullable=False),
    sa.Column('successful_approaches', sa.String(), nullable=False),
    sa.Column('failed_approaches', sa.String(), nullable=False),
    sa.Column('learning_style', sa.String(), nullable=False),
    sa.Column('peak_activity_hours', sa.String(), nullable=False),
    sa.Column('response_time_expectations', sa.String(), nullable=False),
    sa.Column('follow_up_frequency', sa.String(), nullable=False),
    sa.Column('complexity_level', sa.String(), nullable=False),
    sa.Column('example_requirements', sa.String(), nullable=False),
    sa.Column('visual_vs_text', sa.String(), nullable=False),
    sa.Column('frustration_triggers', sa.String(), nullable=False),
    sa.Column('motivation_factors', sa.String(), nullable=False),
    sa.Column('stress_patterns', sa.String(), nullable=False),
    sa.Column('completion_rates_by_task_type', sa.String(), nullable=False),
    sa.Column('observation_count', sa.Integer(), nullable=False),
    sa.Column('last_observation_at', sa.DateTime(), nullable=True),
    sa.Column('confidence_score', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_userobservation_user_id'), 'userobservation', ['user_id'], unique=False)
    op.create_index(op.f('ix_userobservation_tenant_id'), 'userobservation', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_userobservation_tenant_id'), table_name='userobservation')
    op.drop_index(op.f('ix_userobservation_user_id'), table_name='userobservation')
    op.drop_table('userobservation')
