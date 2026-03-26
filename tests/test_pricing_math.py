import os
import pytest
import asyncio

from src.services.pricing.cost_tracker import CostTracker
from src.core.redis import get_redis_client


@pytest.mark.asyncio
async def test_pricing_summarize_math_and_rounding(monkeypatch):
    # Set non-zero pricing rates
    monkeypatch.setenv("PRICE_PER_1K_INPUT_TOKENS", "1.0")
    monkeypatch.setenv("PRICE_PER_1K_OUTPUT_TOKENS", "2.0")
    monkeypatch.setenv("PRICE_PER_API_CALL", "0.5")
    monkeypatch.setenv("PRICE_PER_MB_INBOUND", "0.1")
    monkeypatch.setenv("PRICE_PER_MB_OUTBOUND", "0.2")
    monkeypatch.setenv("PRICE_PER_MS_COMPUTE", "0.0001")

    # Use in-memory fake by pointing REDIS_URL to a non-connecting schema and monkeypatch RedisClient methods
    r = get_redis_client()
    store = {}

    async def _incr(key: str, amount: int = 1):
        store[key] = int(store.get(key, 0)) + amount
        return store[key]

    async def _get(key: str, default=None):
        return store.get(key, default)

    # Monkeypatch RedisClient methods used by CostTracker
    r.incr = _incr  # type: ignore
    r.get = _get    # type: ignore

    tracker = CostTracker(redis_client=r)
    job_id = "job_test_price"
    # Tokens: 1500 in, 500 out → 1.5*1 + 0.5*2 = 1.5 + 1.0 = 2.5
    await tracker.record_tokens(job_id, input_tokens=1500, output_tokens=500)
    # API calls: 3 → 3*0.5 = 1.5
    for _ in range(3):
        await tracker.record_api_call(job_id, provider="exa")
    # Data: 1.0 MB in, 2.0 MB out → 0.1*1 + 0.2*2 = 0.1 + 0.4 = 0.5
    await tracker.record_data_transfer(job_id, mb_in=1.0, mb_out=2.0)
    # Compute: 1000 ms → 1000*0.0001 = 0.1
    await tracker.record_compute_time_ms(job_id, 1000)

    summary = await tracker.summarize(job_id)
    total = summary["total_cost"]
    assert abs(total - (2.5 + 1.5 + 0.5 + 0.1)) < 1e-6


