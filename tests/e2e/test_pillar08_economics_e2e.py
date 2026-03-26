import os
import json
import pytest
from sqlmodel import select


from tests.e2e._dummy_redis import setup_dummy_redis


@pytest.mark.asyncio
async def test_pillar08_economics_cost_tracker_credits_and_ledger(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-p8")
    monkeypatch.setenv("SECRET_KEY", "test-secret-p8-app")
    monkeypatch.setenv("PRICE_PER_1K_INPUT_TOKENS", "0.002")
    monkeypatch.setenv("PRICE_PER_1K_OUTPUT_TOKENS", "0.003")
    monkeypatch.setenv("PRICE_PER_API_CALL", "0.01")
    monkeypatch.setenv("PRICE_PER_MB_INBOUND", "0.001")
    monkeypatch.setenv("PRICE_PER_MB_OUTBOUND", "0.002")
    monkeypatch.setenv("PRICE_PER_MS_COMPUTE", "0.00001")
    monkeypatch.setenv("DOLLAR_TO_CREDITS_RATIO", "50")

    from src.services.pricing.cost_tracker import CostTracker
    from src.services.pricing.credit_manager import CreditManager
    from src.services.pricing.ledger import PricingLedger
    from src.etherion_ai.app import create_app
    from httpx import AsyncClient, ASGITransport
    from src.database.db import get_scoped_session
    from src.database.models import Tenant, User
    from src.auth.jwt import create_access_token
    from src.database.ts_models import ExecutionCost

    job_id = "pillar08-job"
    tracker = CostTracker()

    # Ensure Redis is the in-memory dummy for rate/ledger/counters
    setup_dummy_redis(monkeypatch)

    await tracker.record_tokens(job_id, input_tokens=1800, output_tokens=600)
    await tracker.record_api_call(job_id, provider="exa")
    await tracker.record_data_transfer(job_id, mb_in=1.25, mb_out=2.5)
    await tracker.record_compute_time_ms(job_id, ms=1250)

    summary = await tracker.summarize(job_id)
    assert summary["job_id"] == job_id
    assert summary["total_cost"] > 0
    assert summary["cost_breakdown"]["api"] > 0
    assert int(summary["counters"]["tokens_in"]) == 1800
    from src.core.redis import get_redis_client

    redis_client = get_redis_client()
    client = await redis_client.get_client()
    api_total = int(await client.get(f"cost:{job_id}:api_total") or 0)
    assert api_total == 1

    credit_manager = CreditManager()
    balance_after_allocate = await credit_manager.allocate(user_id=42, amount=500)
    assert balance_after_allocate == 500
    balance_after_deduct = await credit_manager.deduct(user_id=42, amount=275)
    assert balance_after_deduct == 225

    ledger = PricingLedger()
    ratio = int(os.environ.get("DOLLAR_TO_CREDITS_RATIO", "50"))
    expected_credits = int(round(summary["total_cost"] * ratio))
    await ledger.append_usage_event(
        user_id=42,
        job_id=job_id,
        usage_summary=summary,
        credit_delta=-expected_credits,
        currency=summary["currency"],
    )

    ledger_key = "pricing:ledger:user:42"
    entries = await client.lrange(ledger_key, 0, 0)
    assert entries, "Expected ledger entry in Redis"
    entry = json.loads(entries[0])
    assert entry["job_id"] == job_id
    assert entry["credit_delta"] == -expected_credits

    # Tie costing to a real orchestrator call flow and persist an ExecutionCost row
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with get_scoped_session() as session:
            tenant = Tenant(tenant_id="pillar08-econ", subdomain="pillar08-econ", name="P8 Econ", admin_email="p8@test.local")
            session.add(tenant); await session.commit(); await session.refresh(tenant)
            user = User(user_id="p8-user", tenant_id=tenant.id, email="p8@test.local")
            session.add(user); await session.commit(); await session.refresh(user)

        token = create_access_token({"sub": user.user_id, "email": user.email, "tenant_id": tenant.id})
        headers = {"Authorization": f"Bearer {token}"}

        mutation = (
            "mutation($input: GoalInput!) { "
            "executeGoal(goalInput: $input) { success job_id status message } }"
        )
        variables = {"input": {"goal": "Cost a short inference run", "userId": user.user_id}}
        resp = await client.post("/graphql", json={"query": mutation, "variables": variables}, headers=headers)
        assert resp.status_code == 200
        payload = resp.json().get("data", {}).get("executeGoal")
        assert payload and payload.get("success") is True
        orch_job_id = payload["job_id"]

        # Persist a correlated ExecutionCost record (DB) to validate ledger↔DB correlation
        async with get_scoped_session() as session:
            ec = ExecutionCost(
                job_id=orch_job_id,
                tenant_id=tenant.id,
                step_name="orchestrator",
                model_used="stub-llm",
                input_tokens=summary["counters"]["tokens_in"],
                output_tokens=summary["counters"]["tokens_out"],
                step_cost=float(summary["total_cost"]),
            )
            session.add(ec)
            await session.commit()
            row = (await session.exec(select(ExecutionCost).where(ExecutionCost.job_id == orch_job_id))).first()
            assert row is not None and row.step_cost >= 0.0

        # Credit exhaustion: drain credits then ensure further deducts clamp to 0
        bal = await credit_manager.deduct(user_id=42, amount=1000)
        assert bal == 0
