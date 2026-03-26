import os
import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient
from httpx import ASGITransport

# Ensure secret set before importing create_access_token
os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")

from src.auth.jwt import create_access_token
from src.etherion_ai.middleware.tenant_middleware import tenant_middleware


@pytest.mark.asyncio
async def test_tenant_middleware_sets_tenant_id():

    app = FastAPI()

    @app.middleware("http")
    async def _mw(request: Request, call_next):
        # chain tenant middleware then route
        return await tenant_middleware(request, call_next)

    @app.get("/me")
    async def me(request: Request):
        return {"tenant_id": getattr(request.state, "tenant_id", None)}

    token = create_access_token({"sub": "u-xyz", "email": "u@example.com", "tenant_id": 42})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["tenant_id"] == 42
