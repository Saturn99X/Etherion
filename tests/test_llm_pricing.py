import pytest

from src.services.pricing.llm_pricing import estimate_tokens_cost


def test_flash_live_with_caching():
    # 1M input tokens at flash live: 0.50 per 1M, 1M caching: 0.03 per 1M
    cost = estimate_tokens_cost(
        provider="vertex",
        model="gemini-2.5-flash",
        input_tokens=1_000_000,
        output_tokens=0,
        mode="live",
        caching_tokens=1_000_000,
    )
    assert cost == pytest.approx(0.53, rel=1e-6)


def test_pro_tier_threshold():
    # 250k input tokens -> higher tier for pro: 2.50 per 1M
    cost = estimate_tokens_cost(
        provider="vertex",
        model="gemini-2.5-pro",
        input_tokens=250_000,
        output_tokens=0,
    )
    assert cost == pytest.approx(0.625, rel=1e-6)
