# src/utils/llm_providers/openai.py
from __future__ import annotations
import os
from typing import Any, Dict

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI provider using API key from environment.

    Lazy-imports langchain_openai.ChatOpenAI to avoid hard deps when unused.
    """

    def load(self, *, model: str, config: Dict[str, Any]) -> Any:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OpenAIProvider requires OPENAI_API_KEY to be set.")

        try:
            from langchain_openai import ChatOpenAI
        except Exception as e:
            raise RuntimeError(
                "langchain_openai is required for OpenAI models. Install it and retry."
            ) from e

        model_name = config.get("model_name", model)
        temperature = float(config.get("temperature", 0.7))
        timeout = int(config.get("timeout", 60))

        llm = ChatOpenAI(model=model_name, temperature=temperature, timeout=timeout, api_key=api_key)
        # Annotate with provider/model metadata so callers can report accurately
        try:
            setattr(llm, "provider", "openai")
            setattr(llm, "model_name", model_name)
        except Exception:
            # Best-effort; do not fail construction if attributes cannot be set
            pass

        # Optional probe
        if config.get("probe", False):
            llm.invoke("ping")
        return llm
