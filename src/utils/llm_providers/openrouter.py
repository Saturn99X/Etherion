"""OpenRouter LLM provider — unified API for 200+ models."""
from __future__ import annotations
import os
from typing import Any, Dict, Optional

from .base import LLMProvider, ProviderSpec

_OPENROUTER_MODELS = {
    "default": "openai/gpt-4o",
    "fast": "openai/gpt-4o-mini",
    "smart": "anthropic/claude-sonnet-4",
    "claude-sonnet-4": "anthropic/claude-sonnet-4",
    "claude-haiku": "anthropic/claude-3-5-haiku",
    "gpt-4o": "openai/gpt-4o",
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "llama-3-70b": "meta-llama/llama-3-70b-instruct",
    "llama-3-8b": "meta-llama/llama-3-8b-instruct",
    "mixtral": "mistralai/mixtral-8x7b-instruct",
}


class OpenRouterProvider(LLMProvider):
    spec = ProviderSpec(
        name="openrouter",
        display_name="OpenRouter",
        required_env=("OPENROUTER_API_KEY",),
        models=_OPENROUTER_MODELS,
    )

    def load(self, *, model: str = "default", config: Optional[Dict[str, Any]] = None) -> Any:
        model_id = _OPENROUTER_MODELS.get(model, model)
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model_id,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            **(config or {}),
        )
        try:
            setattr(llm, "provider", "openrouter")
            setattr(llm, "model_name", model_id)
        except Exception:
            pass
        return llm

    def is_available(self) -> bool:
        return bool(os.getenv("OPENROUTER_API_KEY"))