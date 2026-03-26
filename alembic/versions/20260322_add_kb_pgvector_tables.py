"""Add knowledgebase and document tables with pgvector support.

Revision ID: 20260322_add_kb_pgvector
Revises: 20260316_remove_billing
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = '20260322_add_kb_pgvector'
down_revision = '20260316_remove_billing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Install pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'knowledgebase',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('kb_id', sa.String, nullable=False),
        sa.Column('tenant_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('kb_type', sa.String, server_default='project', nullable=False),
        sa.Column('project_id', sa.String, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_knowledgebase_kb_id', 'knowledgebase', ['kb_id'], unique=True)
    op.create_index('ix_knowledgebase_tenant_id', 'knowledgebase', ['tenant_id'])
    op.create_index('ix_knowledgebase_project_id', 'knowledgebase', ['project_id'])

    op.create_table(
        'document',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('doc_id', sa.String, nullable=False),
        sa.Column('kb_id', sa.Integer, sa.ForeignKey('knowledgebase.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', sa.Integer, nullable=False),
        sa.Column('text_chunk', sa.Text, nullable=False),
        sa.Column('metadata_json', sa.Text, nullable=True),
        sa.Column('storage_uri', sa.String, nullable=True),
        sa.Column('filename', sa.String, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_document_doc_id', 'document', ['doc_id'], unique=True)
    op.create_index('ix_document_kb_id', 'document', ['kb_id'])
    op.create_index('ix_document_tenant_id', 'document', ['tenant_id'])

    # Add pgvector embedding column (raw SQL — SQLAlchemy can't render vector DDL)
    op.execute("ALTER TABLE document ADD COLUMN embedding vector(1536)")

    # HNSW index for fast cosine similarity search
    op.execute("CREATE INDEX document_embedding_hnsw ON document USING hnsw (embedding vector_cosine_ops)")

    # Row Level Security
    op.execute("ALTER TABLE knowledgebase ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY knowledgebase_tenant_isolation ON knowledgebase
        USING (tenant_id = current_setting('app.tenant_id', true)::integer)
    """)
    op.execute("""
        CREATE POLICY document_tenant_isolation ON document
        USING (tenant_id = current_setting('app.tenant_id', true)::integer)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS document_tenant_isolation ON document")
    op.execute("DROP POLICY IF EXISTS knowledgebase_tenant_isolation ON knowledgebase")
    op.drop_index('document_embedding_hnsw', table_name='document')
    op.drop_table('document')
    op.drop_table('knowledgebase')
