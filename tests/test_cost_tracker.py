import os
import pytest

from src.services.pricing.cost_tracker import CostTracker


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, expire=None):
        self.store[key] = value
        return True

    async def get(self, key, default=None):
        return self.store.get(key, default)

    async def incr(self, key, amount=1):
        self.store[key] = int(self.store.get(key, 0) or 0) + int(amount)
        return self.store[key]


@pytest.mark.asyncio
async def test_cost_tracker_summarize_components():
    # CostTracker requires these env vars even when LLM-specific pricing is used.
    os.environ["PRICE_PER_1K_INPUT_TOKENS"] = "0"
    os.environ["PRICE_PER_1K_OUTPUT_TOKENS"] = "0"
    os.environ["PRICE_PER_API_CALL"] = "0"
    os.environ["PRICE_PER_MB_INBOUND"] = "0"
    os.environ["PRICE_PER_MB_OUTBOUND"] = "0"
    os.environ["PRICE_PER_MS_COMPUTE"] = "0"

    r = FakeRedis()
    ct = CostTracker(redis_client=r)
    job_id = "job-test-1"
    tenant_id = "t1"

    # LLM context and tokens
    # Mix legacy + tenant-scoped writes to ensure summarize(tenant_id=...) merges both.
    await ct.set_llm_context(job_id, provider="vertex", model="gemini-3-pro-preview", tenant_id=tenant_id)
    await ct.record_tokens(job_id, input_tokens=100_000, output_tokens=50_000)  # legacy key

    # Vertex AI Search enterprise query
    await ct.record_vertex_search(job_id, enterprise_q=1, tenant_id=tenant_id)

    # BigQuery scan: 1 TB
    await ct.record_bigquery_scan(job_id, bytes_scanned=1024 ** 4, tenant_id=tenant_id)

    # EXA search + contents
    await ct.record_exa_search(job_id, kind="neural", results=20, tenant_id=tenant_id)  # 1 in 1-25 bucket
    await ct.record_exa_contents(job_id, kind="text", pages=1000, tenant_id=tenant_id)  # 1k pages

    summary = await ct.summarize(job_id, tenant_id=tenant_id)
    cb = summary["cost_breakdown"]

    # LLM tokens: pro tier (<=200k input): input 0.125 + output 0.5 = 0.625
    assert cb["tokens"] == pytest.approx(0.625, rel=1e-6)

    # Vertex Search: 1 enterprise query -> 4.0/1000 = 0.004
    assert cb["vertex_search"] == pytest.approx(0.004, rel=1e-6)

    # BigQuery: 1 TB * $5/TB = 5.0
    assert cb["bigquery"] == pytest.approx(5.0, rel=1e-6)

    # EXA: neural 1 query (1-25 bucket): 5/1000 = 0.005 + contents text 1k pages: 1.0 => 1.005
    assert cb["exa"] == pytest.approx(1.005, rel=1e-6)

    # Total: 0.625 + 0.004 + 5.0 + 1.005 = 6.634 (no other costs set)
    assert summary["total_cost"] == pytest.approx(6.634, rel=1e-6)
