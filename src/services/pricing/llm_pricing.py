# src/services/pricing/llm_pricing.py
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict, Optional

# Ensure pricing secrets are loaded from GSM before reading env vars
from src.services.pricing.pricing_secrets_loader import ensure_pricing_secrets_loaded
ensure_pricing_secrets_loaded()

# Currency default can be overridden via env to support multi-currency later.
DEFAULT_CURRENCY = os.getenv("PRICING_CURRENCY", "USD")


def _must_env_float(name: str) -> float:
    """Return float value for required env var or raise a clear error.

    Removing silent 0.0 fallbacks: pricing must be explicitly configured via env/GSM.
    """
    val = os.environ.get(name)
    if val is None or str(val).strip() == "":
        raise RuntimeError(f"Missing required pricing environment variable: {name}")
    try:
        return float(val)
    except Exception as e:
        raise RuntimeError(f"Invalid float for env {name}: {val}") from e


@dataclass(frozen=True)
class ModelPricing:
    provider: str           # e.g., "vertex", "openai"
    model: str              # e.g., "gemini-2.5-pro", "gpt-4o"
    currency: str = "USD"
    # token prices per 1M tokens
    input_per_1m_tokens: float = 0.0
    output_per_1m_tokens: float = 0.0


# Static defaults (can be overridden via env)
_DEFAULTS: Dict[str, ModelPricing] = {
    # Vertex/Gemini (accurate as of Jan 2026 - rates per 1M tokens)
    "vertex/gemini-3-flash-preview": ModelPricing(
        provider="vertex", model="gemini-3-flash-preview", currency="USD",
        input_per_1m_tokens=0.30, output_per_1m_tokens=2.50
    ),
    "vertex/gemini-3-pro-preview": ModelPricing(
        provider="vertex", model="gemini-3-pro-preview", currency="USD",
        input_per_1m_tokens=1.25, output_per_1m_tokens=10.00
    ),
    "vertex/gemini-2.5-pro": ModelPricing(
        provider="vertex", model="gemini-2.5-pro", currency="USD",
        # Base tier ≤200K tokens: $2.00 input / $12.00 output
        # Higher tier >200K tokens: $4.00 input / $18.00 output (handled dynamically in estimate_tokens_cost)
        input_per_1m_tokens=2.00, output_per_1m_tokens=12.00
    ),
    # Thinking mode surcharge for gemini models
    "vertex/gemini-3-flash-preview-thinking": ModelPricing(
        provider="vertex", model="gemini-3-flash-preview", currency="USD",
        input_per_1m_tokens=0.30, output_per_1m_tokens=3.50
    ),
    "vertex/gemini-3-pro-preview-thinking": ModelPricing(
        provider="vertex", model="gemini-3-pro-preview", currency="USD",
        input_per_1m_tokens=1.25, output_per_1m_tokens=15.00
    ),
    # OpenAI (illustrative; adjust as provider updates pricing)
    "openai/gpt-4o": ModelPricing(
        provider="openai", model="gpt-4o", currency="USD",
        input_per_1m_tokens=5.00, output_per_1m_tokens=15.00
    ),
    "openai/gpt-4o-mini": ModelPricing(
        provider="openai", model="gpt-4o-mini", currency="USD",
        input_per_1m_tokens=0.15, output_per_1m_tokens=0.60
    ),
}


def _env_override_key(provider: str, model: str, field: str) -> str:
    # Example: LLM_PRICE_OPENAI_GPT_4O_INPUT_PER_1M
    prov = provider.upper()
    mod = model.replace("-", "_").replace(".", "_").upper()
    fld = field.upper()
    return f"LLM_PRICE_{prov}_{mod}_{fld}"


def get_model_pricing(provider: str, model: str) -> ModelPricing:
    key = f"{provider}/{model}"
    base_pricing = _DEFAULTS.get(key)
    # Fallback to zero-priced model when absent
    if not base_pricing:
        base_pricing = ModelPricing(provider=provider, model=model, currency=DEFAULT_CURRENCY)

    # Apply env overrides if present
    inp = float(os.getenv(_env_override_key(provider, model, "INPUT_PER_1M"), base_pricing.input_per_1m_tokens))
    out = float(os.getenv(_env_override_key(provider, model, "OUTPUT_PER_1M"), base_pricing.output_per_1m_tokens))

    return ModelPricing(
        provider=provider,
        model=model,
        currency=base_pricing.currency,
        input_per_1m_tokens=inp,
        output_per_1m_tokens=out,
    )


def estimate_tokens_cost(
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    mode: Optional[str] = None,  # e.g., "thinking"
    caching_tokens: int = 0,
) -> float:
    """Estimate LLM token-related cost with model-specific tiers and modes.

    Implements accurate Gemini pricing per official Google Cloud documentation.
    Falls back to baseline per-1M rates when unknown.
    """

    # Normalize
    prov = provider.lower()
    mod = model.lower()
    inp = int(input_tokens)
    out = int(output_tokens)
    cache = int(caching_tokens)

    effective_model = mod
    if prov == "vertex" and mode == "thinking" and effective_model in {"gemini-3-pro-preview", "gemini-3-flash-preview"}:
        effective_model = f"{effective_model}-thinking"

    mp = get_model_pricing(provider, effective_model)
    tokens_cost = float((inp / 1_000_000.0) * mp.input_per_1m_tokens + (out / 1_000_000.0) * mp.output_per_1m_tokens)

    caching_rate_by_model = {
        "gemini-3-pro-preview": 0.125,
        "gemini-3-pro-preview-thinking": 0.125,
        "gemini-3-flash-preview": 0.03,
        "gemini-3-flash-preview-thinking": 0.03,
    }
    caching_rate_m = float(caching_rate_by_model.get(effective_model, 0.0))
    cache_cost = float((cache / 1_000_000.0) * caching_rate_m) if cache > 0 and caching_rate_m > 0 else 0.0

    return float(tokens_cost + cache_cost)


def estimate_usage_cost(
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    api_calls: int = 0,
    kb_in: int = 0,
    kb_out: int = 0,
    compute_ms: int = 0,
    mode: Optional[str] = None,
    caching_tokens: int = 0,
) -> float:
    """Estimate total cost using model-specific token rates plus platform-wide costs."""
    tokens_cost = estimate_tokens_cost(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        mode=mode,
        caching_tokens=caching_tokens,
    )
    api_cost = api_calls * _must_env_float("PRICE_PER_API_CALL")
    data_cost_in = (kb_in / 1024.0) * _must_env_float("PRICE_PER_MB_INBOUND")
    data_cost_out = (kb_out / 1024.0) * _must_env_float("PRICE_PER_MB_OUTBOUND")
    data_cost = data_cost_in + data_cost_out
    compute_cost = compute_ms * _must_env_float("PRICE_PER_MS_COMPUTE")
    return float(tokens_cost + api_cost + data_cost + compute_cost)
