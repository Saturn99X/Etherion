"""Anthropic Claude LLM provider."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import LLMProvider, ProviderSpec

_DEFAULT_MODELS = {
    "default": "claude-sonnet-4-5",
    "fast": "claude-haiku-4-5-20251001",
    "smart": "claude-opus-4-6",
}


class AnthropicProvider(LLMProvider):
    spec = ProviderSpec(
        name="anthropic",
        display_name="Anthropic Claude",
        required_env=("ANTHROPIC_API_KEY",),
    )

    def load(self, model: str = "default", config: Optional[Dict[str, Any]] = None):
        from langchain_anthropic import ChatAnthropic

        model_id = _DEFAULT_MODELS.get(model, model)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        return ChatAnthropic(model=model_id, api_key=api_key, **(config or {}))

    def is_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY"))
