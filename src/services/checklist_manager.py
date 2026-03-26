"""Checklist CRUD service."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlmodel import select


class ChecklistManager:
    async def create_checklist(
        self,
        tenant_id: int,
        title: str,
        items: List[str],
        user_id: Optional[int] = None,
        description: Optional[str] = None,
    ):
        from src.database.db import get_session
        from src.database.models.checklist import Checklist, ChecklistItem

        async for session in get_session():
            checklist = Checklist(
                checklist_id=f"cl_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                user_id=user_id,
                title=title,
                description=description,
            )
            session.add(checklist)
            await session.flush()

            for idx, text in enumerate(items):
                session.add(ChecklistItem(
                    checklist_id=checklist.id,
                    tenant_id=tenant_id,
                    text=text,
                    order=idx,
                ))

            await session.commit()
            await session.refresh(checklist)
            return checklist
        return None

    async def get_checklist(self, tenant_id: int, checklist_id: str):
        from src.database.db import get_session
        from src.database.models.checklist import Checklist

        async for session in get_session():
            result = await session.execute(
                select(Checklist).where(
                    Checklist.checklist_id == checklist_id,
                    Checklist.tenant_id == tenant_id,
                )
            )
            return result.scalars().first()
        return None

    async def check_item(self, tenant_id: int, item_id: int, checked: bool = True):
        from src.database.db import get_session
        from src.database.models.checklist import ChecklistItem

        async for session in get_session():
            item = await session.get(ChecklistItem, item_id)
            if item and item.tenant_id == tenant_id:
                item.is_checked = checked
                await session.commit()
                await session.refresh(item)
            return item
        return None

    async def list_checklists(self, tenant_id: int, user_id: Optional[int] = None):
        from src.database.db import get_session
        from src.database.models.checklist import Checklist

        async for session in get_session():
            q = select(Checklist).where(Checklist.tenant_id == tenant_id)
            if user_id is not None:
                q = q.where(Checklist.user_id == user_id)
            result = await session.execute(q)
            return result.scalars().all()
        return []

    async def delete_checklist(self, tenant_id: int, checklist_id: str) -> bool:
        from src.database.db import get_session
        from src.database.models.checklist import Checklist, ChecklistItem
        from sqlalchemy import delete

        async for session in get_session():
            cl = await session.execute(
                select(Checklist).where(
                    Checklist.checklist_id == checklist_id,
                    Checklist.tenant_id == tenant_id,
                )
            )
            obj = cl.scalars().first()
            if obj:
                await session.execute(delete(ChecklistItem).where(ChecklistItem.checklist_id == obj.id))
                await session.delete(obj)
                await session.commit()
                return True
        return False
