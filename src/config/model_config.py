"""
Model configuration — maps orchestrator roles to (provider, model) pairs.

All values are read from environment variables with sensible defaults.
Users can override any role's provider and model without touching code.

Usage:
    cfg = get_model_config()
    cfg.orchestrator_provider      # e.g. "bedrock"
    cfg.orchestrator_model         # e.g. "fast"
    cfg.specialist_provider        # e.g. "bedrock"
    cfg.specialist_model           # e.g. "fast"
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ModelConfig:
    orchestrator_provider: str
    orchestrator_model: str
    specialist_provider: str
    specialist_model: str
    embedding_provider: str
    embedding_model: str


def get_model_config() -> ModelConfig:
    return ModelConfig(
        orchestrator_provider=os.getenv("ORCHESTRATOR_PROVIDER", "bedrock"),
        orchestrator_model=os.getenv("ORCHESTRATOR_MODEL", "fast"),
        specialist_provider=os.getenv("SPECIALIST_PROVIDER", "bedrock"),
        specialist_model=os.getenv("SPECIALIST_MODEL", "fast"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "gemini"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-004"),
    )


def get_available_providers() -> Dict[str, Dict[str, List[str]]]:
    """Return all registered providers with their available models.
    
    Returns:
        {"bedrock": {"display": "Amazon Bedrock", "models": ["fast", "default", "smart", ...]},
         "openai": {"display": "OpenAI", "models": ["default", "fast", "smart", "gpt-4o", ...]},
         ...}
    """
    from src.utils.llm_registry import REGISTRY, _load_provider
    result = {}
    for key, reg in REGISTRY.items():
        try:
            spec, provider = _load_provider(key)
            available = bool(provider.is_available()) if hasattr(provider, 'is_available') else False
            model_list = list(spec.models.keys()) if spec.models else []
            result[key] = {
                "display": spec.display_name,
                "models": model_list,
                "available": available,
            }
        except Exception:
            result[key] = {"display": key, "models": [], "available": False}
    return result