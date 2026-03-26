"""Checklist and ChecklistItem SQLModel tables."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class Checklist(SQLModel, table=True):
    __tablename__ = "checklist"

    id: Optional[int] = Field(default=None, primary_key=True)
    checklist_id: str = Field(unique=True, index=True, nullable=False)
    tenant_id: int = Field(foreign_key="tenant.id", index=True, nullable=False)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    title: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    is_complete: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    items: List["ChecklistItem"] = Relationship(back_populates="checklist")


class ChecklistItem(SQLModel, table=True):
    __tablename__ = "checklistitem"

    id: Optional[int] = Field(default=None, primary_key=True)
    checklist_id: int = Field(foreign_key="checklist.id", index=True, nullable=False)
    tenant_id: int = Field(index=True, nullable=False)
    text: str = Field(nullable=False)
    is_checked: bool = Field(default=False)
    order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    checklist: Optional[Checklist] = Relationship(back_populates="items")
