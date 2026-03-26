"""KnowledgeBase and Document SQLModel tables with pgvector embedding column."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel


def _embedding_column():
    try:
        from pgvector.sqlalchemy import Vector
        dim = int(os.getenv("KB_EMBEDDING_DIM", "1536"))
        return Column(Vector(dim), nullable=True)
    except ImportError:
        # pgvector not installed; fall back to JSON text for schema compat
        return Column(Text, nullable=True)


class KnowledgeBase(SQLModel, table=True):
    __tablename__ = "knowledgebase"

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: str = Field(unique=True, index=True, nullable=False)
    tenant_id: int = Field(index=True, nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    kb_type: str = Field(default="project")  # project | personal
    project_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    documents: List["Document"] = Relationship(back_populates="knowledge_base")


class Document(SQLModel, table=True):
    __tablename__ = "document"

    id: Optional[int] = Field(default=None, primary_key=True)
    doc_id: str = Field(unique=True, index=True, nullable=False)
    kb_id: int = Field(foreign_key="knowledgebase.id", index=True, nullable=False)
    tenant_id: int = Field(index=True, nullable=False)
    text_chunk: str = Field(sa_column=Column(Text, nullable=False))
    embedding: Optional[Any] = Field(default=None, sa_column=_embedding_column())
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    storage_uri: Optional[str] = Field(default=None)
    filename: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    knowledge_base: Optional[KnowledgeBase] = Relationship(back_populates="documents")
