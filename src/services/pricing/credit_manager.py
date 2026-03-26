import logging
from typing import Optional
from datetime import datetime

from src.core.redis import RedisClient
import src.core.redis as redis_mod
from src.database.db import get_scoped_session
from src.database.ts_models import TenantCreditBalance
from sqlmodel import select

logger = logging.getLogger(__name__)


class CreditManager:
    """
    Manages user credits using Redis with tenant isolation.
    All operations are zero-rated; balances start at 0 until allocated.
    """

    def __init__(self, redis_client: Optional[RedisClient] = None):
        self._override_redis = redis_client

    async def _key(self, user_id: int, tenant_id: Optional[str] = None) -> str:
        """Return the Redis key for a user's credit balance.

        If tenant_id is provided, scope the key per-tenant as
        `credits:{tenant_id}:user:{user_id}`; otherwise, fall back to the
        legacy global key `credits:user:{user_id}` for backward compatibility.
        """
        if tenant_id:
            return f"credits:{tenant_id}:user:{user_id}"
        return f"credits:user:{user_id}"

    async def get_balance(self, user_id: int, tenant_id: Optional[str] = None) -> int:
        """Return DB-authoritative balance; fall back to Redis if DB empty."""
        # Try DB first
        try:
            if tenant_id is not None:
                async with get_scoped_session() as session:
                    rec = await session.exec(
                        select(TenantCreditBalance).where(
                            TenantCreditBalance.tenant_id == int(tenant_id),
                            TenantCreditBalance.user_id == int(user_id),
                        )
                    )
                    row = rec.first()
                    if row:
                        # Keep Redis cache in sync
                        key = await self._key(user_id, tenant_id)
                        redis = self._override_redis or redis_mod.get_redis_client()
                        try:
                            await redis.set(key, int(row.balance_credits))
                        except Exception:
                            pass
                        return int(row.balance_credits or 0)
        except Exception:
            pass

        # Fallback to Redis cache
        redis = self._override_redis or redis_mod.get_redis_client()
        value = await redis.get(await self._key(user_id, tenant_id), 0)
        return int(value or 0)

    async def allocate(self, user_id: int, amount: int, tenant_id: Optional[str] = None) -> int:
        """Increase balance in DB; mirror to Redis cache."""
        amount = int(amount or 0)
        if amount == 0:
            return await self.get_balance(user_id, tenant_id)
        new_balance = None
        if tenant_id is not None:
            try:
                async with get_scoped_session() as session:
                    rec = await session.exec(
                        select(TenantCreditBalance).where(
                            TenantCreditBalance.tenant_id == int(tenant_id),
                            TenantCreditBalance.user_id == int(user_id),
                        )
                    )
                    row = rec.first()
                    if not row:
                        row = TenantCreditBalance(tenant_id=int(tenant_id), user_id=int(user_id), balance_credits=0)
                        session.add(row)
                    row.balance_credits = int(row.balance_credits or 0) + amount
                    row.updated_at = datetime.utcnow()
                    new_balance = int(row.balance_credits)
            except Exception:
                new_balance = None

        # Mirror to Redis (cache). If DB path failed or tenant_id absent, fall back to incr.
        redis = self._override_redis or redis_mod.get_redis_client()
        key = await self._key(user_id, tenant_id)
        try:
            if new_balance is not None:
                await redis.set(key, int(new_balance))
                return int(new_balance)
        except Exception:
            pass

        # Fallback purely on Redis
        try:
            new_balance_cache = await redis.incr(key, amount)
            return int(new_balance_cache)
        except Exception:
            return int(new_balance or 0)

    async def deduct(self, user_id: int, amount: int, tenant_id: Optional[str] = None) -> int:
        """Deduct in DB (clamped at 0); mirror result to Redis cache."""
        amount = int(amount or 0)
        if amount <= 0:
            return await self.get_balance(user_id, tenant_id)

        new_balance = None
        if tenant_id is not None:
            try:
                async with get_scoped_session() as session:
                    rec = await session.exec(
                        select(TenantCreditBalance).where(
                            TenantCreditBalance.tenant_id == int(tenant_id),
                            TenantCreditBalance.user_id == int(user_id),
                        )
                    )
                    row = rec.first()
                    cur = int(row.balance_credits) if row else 0
                    nb = cur - amount
                    if nb < 0:
                        nb = 0
                    if not row:
                        row = TenantCreditBalance(tenant_id=int(tenant_id), user_id=int(user_id), balance_credits=nb)
                        session.add(row)
                    else:
                        row.balance_credits = nb
                    row.updated_at = datetime.utcnow()
                    new_balance = int(nb)
            except Exception:
                new_balance = None

        # Mirror to Redis
        redis = self._override_redis or redis_mod.get_redis_client()
        key = await self._key(user_id, tenant_id)
        try:
            if new_balance is not None:
                await redis.set(key, int(new_balance))
                return int(new_balance)
        except Exception:
            pass

        # Fallback to Redis Lua for cache-only
        try:
            client = await redis.get_client()
            script = (
                "local k=KEYS[1]; local amt=tonumber(ARGV[1]); "
                "local cur=tonumber(redis.call('GET', k) or '0'); "
                "if cur<=0 then redis.call('SET', k, 0); return 0 end; "
                "if amt>=cur then redis.call('SET', k, 0); return 0 end; "
                "local nb=cur-amt; redis.call('SET', k, nb); return nb;"
            )
            nb = await client.eval(script, 1, key, int(amount))
            return int(nb or 0)
        except Exception:
            return int(new_balance or 0)


