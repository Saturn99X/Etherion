"""OpenAI LLM provider."""
from __future__ import annotations
import os
from typing import Any, Dict, Optional

from .base import LLMProvider, ProviderSpec

_OPENAI_MODELS = {
    "default": "gpt-4o",
    "fast": "gpt-4o-mini",
    "smart": "gpt-4o",
    "chatgpt": "gpt-4o",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "o3": "o3",
    "o4-mini": "o4-mini",
    "o4": "o4",
}


class OpenAIProvider(LLMProvider):
    spec = ProviderSpec(
        name="openai",
        display_name="OpenAI",
        required_env=("OPENAI_API_KEY",),
        models=_OPENAI_MODELS,
    )

    def load(self, *, model: str = "default", config: Optional[Dict[str, Any]] = None) -> Any:
        model_id = _OPENAI_MODELS.get(model, model)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=model_id, api_key=api_key, **(config or {}))
        try:
            setattr(llm, "provider", "openai")
            setattr(llm, "model_name", model_id)
        except Exception:
            pass
        return llm

    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))