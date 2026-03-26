import os
import types
import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport


class DummySession:
    def __init__(self):
        self.executed = []
        self._commits = 0

    def execute(self, stmt, params=None):
        # Capture raw SQL text and params
        self.executed.append((str(stmt), dict(params or {})))
        return None

    def commit(self):
        self._commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.mark.asyncio
async def test_graphql_auth_middleware_sets_tenant_guc(monkeypatch):
    os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")
    os.environ.setdefault("PG_ENABLE_TENANT_GUC", "true")

    # Import after env is set to satisfy jwt.py guard
    from src.auth.jwt import create_access_token

    # Patch get_db to return our dummy session
    dummy = DummySession()
    monkeypatch.setattr("src.etherion_ai.middleware.auth_context.get_db", lambda: dummy, raising=True)

    # Build app using real stack to exercise middleware
    from src.etherion_ai.app import create_app

    app = create_app()

    token = create_access_token({"sub": "u", "email": "u@x", "tenant_id": 9})

    # Fire a harmless GET over GraphQL so middleware runs but route is non-mutating
    query = {"query": "query { __typename }"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/graphql", headers={"Authorization": f"Bearer {token}"}, params={"query": query["query"]})
        assert r.status_code in (200, 400)  # depends on resolver behavior; middleware is our target

    # Assert a SET app.tenant_id statement attempted
    set_calls = [sql for (sql, params) in dummy.executed if "SET app.tenant_id" in sql]
    assert set_calls, f"Expected SET app.tenant_id; got: {dummy.executed}"
