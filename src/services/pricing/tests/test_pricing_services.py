import pytest
import asyncio

from src.services.pricing.cost_tracker import CostTracker
from src.services.pricing.credit_manager import CreditManager


@pytest.mark.asyncio
async def test_cost_tracker_zero_rates():
    tracker = CostTracker()
    job_id = "job_test"
    await tracker.record_tokens(job_id, input_tokens=123, output_tokens=456)
    await tracker.record_api_call(job_id, provider="slack")
    await tracker.record_data_transfer(job_id, mb_in=1.5)
    await tracker.record_compute_time_ms(job_id, ms=250)
    summary = await tracker.summarize(job_id)
    assert summary["total_cost"] == 0.0
    assert summary["counters"]["tokens_in"] >= 123
    assert summary["counters"]["tokens_out"] >= 456


@pytest.mark.asyncio
async def test_credit_manager_no_negative_balance():
    cm = CreditManager()
    user_id = 999
    balance = await cm.get_balance(user_id)
    assert balance == 0
    await cm.allocate(user_id, 10)
    balance = await cm.get_balance(user_id)
    assert balance >= 10
    new_balance = await cm.deduct(user_id, 99999)
    assert new_balance >= 0


