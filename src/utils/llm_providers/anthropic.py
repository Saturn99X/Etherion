"""Anthropic Claude LLM provider — direct API, NOT Bedrock."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import LLMProvider, ProviderSpec

_ANTHROPIC_MODELS = {
    "default": "claude-sonnet-4-20250514",
    "fast": "claude-3-5-haiku-latest",
    "smart": "claude-opus-4-20250514",
    "claude-sonnet-4-5": "claude-sonnet-4-20250514",
    "claude-haiku-4-5": "claude-3-5-haiku-latest",
    "claude-opus-4-6": "claude-opus-4-20250514",
    "claude-sonnet-4": "claude-sonnet-4-20250514",
    "claude-opus-4": "claude-opus-4-20250514",
}


class AnthropicProvider(LLMProvider):
    spec = ProviderSpec(
        name="anthropic",
        display_name="Anthropic Claude Direct",
        required_env=("ANTHROPIC_API_KEY",),
        models=_ANTHROPIC_MODELS,
    )

    def load(self, *, model: str = "default", config: Optional[Dict[str, Any]] = None) -> Any:
        model_id = _ANTHROPIC_MODELS.get(model, model)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_id, api_key=api_key, **(config or {}))

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))