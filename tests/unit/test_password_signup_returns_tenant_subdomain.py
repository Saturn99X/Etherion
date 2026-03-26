import importlib
import os

import pytest


@pytest.mark.asyncio
async def test_password_signup_returns_tenant_subdomain_even_if_tenant_lookup_fails(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")

    svc = importlib.import_module("src.auth.service")
    dbmod = importlib.import_module("src.database.db")

    # Avoid external dependencies / side effects for this unit test.
    class _DummyCreditManager:
        async def allocate(self, *args, **kwargs):
            return None

    monkeypatch.setattr(
        importlib.import_module("src.services.pricing.credit_manager"),
        "CreditManager",
        _DummyCreditManager,
        raising=True,
    )

    session = dbmod.get_db()
    try:
        original_exec = session.exec

        def exec_wrapper(stmt, *args, **kwargs):
            # Simulate the exact failure mode we saw in production (tenant lookup can fail under
            # RLS/session context). We only want to sabotage the *post-user-create* lookup by id,
            # not the uniqueness check by subdomain.
            s = str(stmt)
            if ("FROM tenant" in s) and ("tenant.id" in s) and ("tenant.subdomain" not in s):
                class _Dummy:
                    def first(self):
                        return None
                return _Dummy()
            return original_exec(stmt, *args, **kwargs)

        session.exec = exec_wrapper  # type: ignore[assignment]

        subdomain = "tmfmmhc"
        out = await svc._password_signup_impl(
            email="unit-tenant-subdomain@test.local",
            password="TestPass123!",
            session=session,
            name="Unit User",
            subdomain=subdomain,
        )

        assert out["user"].tenant_subdomain == subdomain

        from jose import jwt

        payload = jwt.decode(out["access_token"], "testsecret", algorithms=["HS256"])
        assert payload.get("tenant_subdomain") == subdomain
        assert payload.get("tenant_id") is not None
    finally:
        session.close()
