"""
Generic LLM loader facade and backward-compatible Gemini helper.

This module now delegates to `src/utils/llm_registry.py` which provides
lazy-loaded providers and model resolution with strict auth checks per provider.
"""

from typing import Any, Optional
from dotenv import load_dotenv

from src.utils.llm_registry import load_llm

load_dotenv()


def get_llm(*, provider: str, model: Optional[str] = None, tier: Optional[str] = None, config: Optional[dict] = None) -> Any:
    """Load any supported LLM via the central registry.

    Example:
        get_llm(provider="vertex", tier="flash")
        get_llm(provider="openai", model="gpt-4o", config={"temperature": 0.3})
    """
    return load_llm(provider=provider, model=model, tier_or_alias=tier, config=config or {})


def get_gemini_llm(model_tier: str = "pro") -> Any:
    """Backward-compatible loader for Gemini on Vertex AI.

    Delegates to the registry with strict SA enforcement in the Vertex provider.
    """
    return load_llm(provider="vertex", tier_or_alias=model_tier, config={"probe": True})