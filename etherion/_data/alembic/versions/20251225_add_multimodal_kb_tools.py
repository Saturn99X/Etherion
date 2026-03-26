"""Add multimodal KB tools to Tool registry

Revision ID: 20251225_mmkb
Revises: 
Create Date: 2025-12-25

Registers the multimodal knowledge base tools:
- multimodal_kb_search: Cross-modal search (text query finds docs AND images)
- fetch_document_content: On-demand GCS content retrieval
- image_search_by_image: Reverse image search
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '20251225_mmkb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MULTIMODAL_TOOLS = [
    {
        "name": "multimodal_kb_search",
        "description": (
            "Search the multimodal knowledge base using 1408-D embeddings. "
            "Enables CROSS-MODAL search: a text query can retrieve both relevant documents "
            "AND images because they share the same vector space. Use search_type='all' for "
            "combined results, 'docs' for documents only, or 'images' for images only. "
            "Results include gcs_uri for on-demand content fetch."
        ),
        "status": "STABLE",
        "category": "knowledge",
        "version": "1.0.0",
        "requires_auth": False,
        "is_custom_agent_executor": False,
    },
    {
        "name": "fetch_document_content",
        "description": (
            "Fetch full document content from GCS after multimodal_kb_search. "
            "The multimodal KB stores only embeddings and gcs_uri - use this tool "
            "to retrieve actual document text when needed. Set parse_content=True "
            "to get parsed markdown, False for raw bytes."
        ),
        "status": "STABLE",
        "category": "knowledge",
        "version": "1.0.0",
        "requires_auth": False,
        "is_custom_agent_executor": False,
    },
    {
        "name": "image_search_by_image",
        "description": (
            "Reverse image search using an image as query. Because documents and images "
            "are in the same 1408-D vector space, an image query can find: (1) similar "
            "images (visual similarity), and (2) related documents (semantic similarity). "
            "Use case: user uploads a chart, find the source document."
        ),
        "status": "STABLE",
        "category": "knowledge",
        "version": "1.0.0",
        "requires_auth": False,
        "is_custom_agent_executor": False,
    },
]


def upgrade() -> None:
    """Register multimodal KB tools in the database."""
    conn = op.get_bind()
    
    # Check if tool table exists
    inspector = sa.inspect(conn)
    if 'tool' not in inspector.get_table_names():
        return  # Tool table not yet created
    
    now = datetime.utcnow()
    
    for tool in MULTIMODAL_TOOLS:
        # Check if tool already exists
        result = conn.execute(
            sa.text("SELECT id FROM tool WHERE name = :name"),
            {"name": tool["name"]}
        ).fetchone()
        
        if result:
            # Update existing tool
            conn.execute(
                sa.text("""
                    UPDATE tool SET
                        description = :description,
                        status = :status,
                        category = :category,
                        version = :version,
                        last_updated_at = :updated_at
                    WHERE name = :name
                """),
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "status": tool["status"],
                    "category": tool["category"],
                    "version": tool["version"],
                    "updated_at": now,
                }
            )
        else:
            # Insert new tool
            conn.execute(
                sa.text("""
                    INSERT INTO tool (
                        name, description, status, category, version,
                        requires_auth, is_custom_agent_executor,
                        created_at, last_updated_at
                    ) VALUES (
                        :name, :description, :status, :category, :version,
                        :requires_auth, :is_custom_agent_executor,
                        :created_at, :last_updated_at
                    )
                """),
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "status": tool["status"],
                    "category": tool["category"],
                    "version": tool["version"],
                    "requires_auth": tool["requires_auth"],
                    "is_custom_agent_executor": tool["is_custom_agent_executor"],
                    "created_at": now,
                    "last_updated_at": now,
                }
            )


def downgrade() -> None:
    """Remove multimodal KB tools from database."""
    conn = op.get_bind()
    
    for tool in MULTIMODAL_TOOLS:
        conn.execute(
            sa.text("DELETE FROM tool WHERE name = :name"),
            {"name": tool["name"]}
        )
