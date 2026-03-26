import os
import asyncio
import json
import pytest
from httpx import AsyncClient

from tests.e2e._dummy_redis import setup_dummy_redis
from src.auth.jwt import create_access_token


@pytest.mark.asyncio
async def test_dual_search_trace_counts(monkeypatch):
    # Env for deterministic behavior and fallback content
    os.environ.setdefault("JWT_SECRET_KEY", "jwt-test-secret")
    os.environ.setdefault("SECRET_KEY", "server-secret")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "dev-proj")
    os.environ.setdefault("ENABLE_SEARCH_TEST_FALLBACK", "1")

    # Patch redis with in-memory bus
    dummy = setup_dummy_redis(monkeypatch)

    # Patch exa_search to make web results visible when enabled
    async def fake_exa_search(params):
        return {"results": [{"url": "https://example.com", "title": "t"}]}

    import src.tools.unified_research_tool as urt
    monkeypatch.setattr(urt, "exa_search", fake_exa_search, raising=True)

    # Build app
    from src.etherion_ai.app import create_app
    app = create_app()

    # Seed auth token (tenant 5)
    token = create_access_token({"sub": "u-9", "email": "u9@example.com", "tenant_id": 5})

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Execute goal with search_force = False
        q = """
        mutation($input: GoalInput!) { executeGoal(goal_input: $input) { success job_id status message } }
        """
        r0 = await client.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": q,
                "variables": {"input": {"goal": "find docs", "userId": "u-9", "search_force": False}},
            },
        )
        assert r0.status_code == 200
        m0 = r0.json()["data"]["executeGoal"]
        job0 = m0["job_id"]
        assert job0

        # Execute goal with search_force = True
        r1 = await client.post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": q,
                "variables": {"input": {"goal": "find docs", "userId": "u-9", "search_force": True}},
            },
        )
        m1 = r1.json()["data"]["executeGoal"]
        job1 = m1["job_id"]
        assert job1

        # Helper to await a DUAL_SEARCH event
        async def wait_dual(job_id: str, timeout: float = 5.0):
            ch = f"job_trace_{job_id}"
            q = dummy.subscriptions.setdefault(ch, asyncio.Queue())
            try:
                # Drain any existing events
                drain = True
                while drain:
                    try:
                        q.get_nowait()
                    except Exception:
                        drain = False
                # Wait for up to timeout seconds for DUAL_SEARCH
                end = asyncio.get_event_loop().time() + timeout
                while asyncio.get_event_loop().time() < end:
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    if isinstance(evt, dict) and evt.get("type") == "DUAL_SEARCH":
                        return evt
                return None
            finally:
                pass

        evt0 = await wait_dual(job0)
        evt1 = await wait_dual(job1)

        assert evt0 is not None
        assert evt1 is not None
        c0 = evt0.get("counts") or {}
        c1 = evt1.get("counts") or {}

        # When search_force False, web count should be 0; when True, our fake_exa_search supplies 1
        assert int(c0.get("web", 0)) == 0
        assert int(c1.get("web", 0)) >= 1
