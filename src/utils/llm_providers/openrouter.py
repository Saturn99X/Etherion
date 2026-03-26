"""OpenRouter LLM provider (OpenAI-compatible API)."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import LLMProvider, ProviderSpec


class OpenRouterProvider(LLMProvider):
    spec = ProviderSpec(
        name="openrouter",
        display_name="OpenRouter",
        required_env=("OPENROUTER_API_KEY",),
    )

    def load(self, model: str = "anthropic/claude-sonnet-4-5", config: Optional[Dict[str, Any]] = None):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=model,
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://etherion.ai"),
                "X-Title": os.getenv("OPENROUTER_APP_TITLE", "Etherion"),
            },
            **(config or {}),
        )

    def is_available(self) -> bool:
        return bool(os.getenv("OPENROUTER_API_KEY"))
