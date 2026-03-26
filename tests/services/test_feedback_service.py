import pytest
from src.services.feedback_service import FeedbackService, FeedbackPolicy


@pytest.mark.asyncio
async def test_rate_limit_enforced(monkeypatch):
    svc = FeedbackService(tenant_id=1, user_id=1, policy=FeedbackPolicy(max_comments_per_day_per_tenant=1))

    # First submit should pass (assumes JOB_NOT_FOUND avoided by monkeypatching DB if needed)
    async def fake_submit(job_id, goal, final_output, score, comment):
        # bypass DB by monkeypatching _check_and_increment_rate_limit only
        pass

    # We just test the rate limiter key increments explicitly
    key = await svc._rate_limit_key()
    client = await svc.redis.get_client()
    await client.delete(key)

    await svc._check_and_increment_rate_limit()
    with pytest.raises(ValueError):
        await svc._check_and_increment_rate_limit()


