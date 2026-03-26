import asyncio
import pytest

from src.services.behavior_monitor import BehaviorMonitor, BehaviorPolicy
from src.services.trust_manager import TrustManager, TrustConfig


@pytest.mark.asyncio
async def test_behavior_lockout_memory():
    bm = BehaviorMonitor(BehaviorPolicy(window_seconds=60, max_incidents=2, lockout_seconds=5))
    key = "tenant:1:user:1"
    assert not await bm.is_locked_out(key)
    await bm.record_incident(key)
    assert not await bm.is_locked_out(key)
    await bm.record_incident(key)
    assert await bm.is_locked_out(key)


@pytest.mark.asyncio
async def test_trust_adjustment():
    tm = TrustManager(TrustConfig(default_score=50, high_trust_threshold=70, low_trust_threshold=30))
    key = "tenant:1:user:2"
    adj = await tm.get_threshold_adjustment(key)
    assert adj == 0
    await tm.adjust_score(key, +40)  # score 90
    adj = await tm.get_threshold_adjustment(key)
    assert adj < 0
    await tm.adjust_score(key, -80)  # score 10
    adj = await tm.get_threshold_adjustment(key)
    assert adj > 0


