# src/utils/llm_providers/base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


class LLMProvider(Protocol):
    """Protocol for an LLM provider loader. Implementations must lazily import SDKs."""

    def load(self, *, model: str, config: Dict[str, Any]) -> Any:  # returns a Runnable/ChatModel
        ...


@dataclass
class ProviderSpec:
    name: str
    display_name: str
    # Key env vars needed to load models for this provider; used for diagnostics
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...] = ()
    # Map of model aliases/tiers to concrete model names
    models: Dict[str, str] | None = None

    def resolve_model(self, model_or_tier: Optional[str], default: str) -> str:
        if not model_or_tier:
            return default
        if self.models and model_or_tier in self.models:
            return self.models[model_or_tier]
        return model_or_tier
