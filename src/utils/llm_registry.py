# src/utils/llm_registry.py
from __future__ import annotations
import importlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .llm_providers.base import ProviderSpec
from .llm_providers.anthropic import AnthropicProvider
from .llm_providers.openrouter import OpenRouterProvider


# Provider specifications (models map tiers/aliases to concrete names)
VERTEX_SPEC = ProviderSpec(
    name="vertex",
    display_name="Google Vertex AI",
    required_env=("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT"),
    optional_env=("GOOGLE_CLOUD_LOCATION", "VERTEX_AI_LOCATION"),
    models={
        # Tiers (Gemini 3 Preview for Jan 2026)
        "flash": "gemini-3-flash-preview",
        "pro": "gemini-3-pro-preview",
        # Explicit versions
        "gemini-3-flash-preview": "gemini-3-flash-preview",
        "gemini-3-pro-preview": "gemini-3-pro-preview",
        # Aliases
        "gemini-flash": "gemini-3-flash-preview",
        "gemini-pro": "gemini-3-pro-preview",
    },
)

OPENAI_SPEC = ProviderSpec(
    name="openai",
    display_name="OpenAI",
    required_env=("OPENAI_API_KEY",),
    optional_env=(),
    models={
        # Aliases/tiers (examples; adjust as needed)
        "chatgpt": "gpt-4o",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "o3": "o3",
        "o4": "o4",
    },
)

GEMINI_SPEC = ProviderSpec(
    name="gemini",
    display_name="Google Gemini",
    required_env=(),
    optional_env=("GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT"),
    models={
        "default": "gemini-2.5-flash",
        "fast": "gemini-2.5-flash",
        "smart": "gemini-2.5-pro",
        "flash": "gemini-2.5-flash",
        "pro": "gemini-2.5-pro",
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.5-pro": "gemini-2.5-pro",
        "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite-preview",
        "gemini-3-flash-preview": "gemini-3-flash-preview",
        "gemini-3-pro-preview": "gemini-3-pro-preview",
    },
)


@dataclass
class RegisteredProvider:
    spec: ProviderSpec
    module_path: str  # python module path to provider loader
    class_name: str   # provider class name in module


BEDROCK_SPEC = ProviderSpec(
    name="bedrock",
    display_name="Amazon Bedrock",
    required_env=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    optional_env=("AWS_REGION", "AWS_SESSION_TOKEN"),
    models={
        "fast": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "default": "global.anthropic.claude-sonnet-4-6",
        "smart": "global.anthropic.claude-sonnet-4-6",
        "sonnet": "global.anthropic.claude-sonnet-4-6",
        "haiku": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "opus": "anthropic.claude-opus-4-6",
        "nova-pro": "amazon.nova-pro-v1:0",
        "nova-lite": "amazon.nova-lite-v1:0",
        "nova-micro": "amazon.nova-micro-v1:0",
        "llama-3-3-70b": "meta.llama3-3-70b-instruct-v1:0",
        "llama-3-1-70b": "meta.llama3-1-70b-instruct-v1:0",
        "mistral-large-3": "mistral.mistral-large-3-675b-instruct",
        "minimax-m2.5": "minimax.minimax-m2.5",
        "minimax-m2.1": "minimax.minimax-m2.1",
        "glm-5": "zai.glm-5",
        "glm-4.7": "zai.glm-4.7",
    },
)

REGISTRY: Dict[str, RegisteredProvider] = {
    "vertex": RegisteredProvider(
        spec=VERTEX_SPEC,
        module_path="src.utils.llm_providers.vertex",
        class_name="VertexProvider",
    ),
    "openai": RegisteredProvider(
        spec=OPENAI_SPEC,
        module_path="src.utils.llm_providers.openai",
        class_name="OpenAIProvider",
    ),
    "gemini": RegisteredProvider(
        spec=GEMINI_SPEC,
        module_path="src.utils.llm_providers.gemini",
        class_name="GeminiProvider",
    ),
    "bedrock": RegisteredProvider(
        spec=BEDROCK_SPEC,
        module_path="src.utils.llm_providers.bedrock",
        class_name="BedrockProvider",
    ),
    "anthropic": RegisteredProvider(
        spec=AnthropicProvider.spec,
        module_path="src.utils.llm_providers.anthropic",
        class_name="AnthropicProvider",
    ),
    "openrouter": RegisteredProvider(
        spec=OpenRouterProvider.spec,
        module_path="src.utils.llm_providers.openrouter",
        class_name="OpenRouterProvider",
    ),
}


def _load_provider(provider_key: str):
    reg = REGISTRY.get(provider_key)
    if not reg:
        raise ValueError(f"Unknown provider '{provider_key}'. Known: {list(REGISTRY)}")
    module = importlib.import_module(reg.module_path)
    cls = getattr(module, reg.class_name)
    return reg.spec, cls()


def get_provider_spec(provider_key: str) -> ProviderSpec:
    if provider_key not in REGISTRY:
        raise ValueError(f"Unknown provider '{provider_key}'")
    return REGISTRY[provider_key].spec


def load_llm(*, provider: str, model: Optional[str] = None, tier_or_alias: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> Any:
    """Load an LLM from a provider with lazy SDK import.

    - provider: 'vertex' | 'openai' | future keys
    - model: preferred concrete model name (overrides tier)
    - tier_or_alias: e.g., 'flash'/'pro' or 'chatgpt'
    - config: provider-specific overrides (temperature, probe, etc.)
    """
    config = config or {}
    spec, loader = _load_provider(provider)

    # Resolve model name
    default_model = next(iter(spec.models.values())) if spec.models else None
    resolved = model or spec.resolve_model(tier_or_alias, default_model or "")
    if not resolved:
        raise ValueError(f"No model resolved for provider '{provider}'. Provide model or tier.")

    # Special case for Gemini 3: must use 'global' location in Jan 2026
    if provider == "vertex" and resolved.startswith("gemini-3"):
        if "location" not in config:
            config["location"] = "global"

    return loader.load(model=resolved, config=config)


# Optional capabilities metadata for classification (context windows, modalities, etc.)
MODEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "vertex/gemini-3-flash-preview": {
        "context_window": 1_000_000,
        "modalities": ["text", "image"],
        "latency": "low",
    },
    "vertex/gemini-3-pro-preview": {
        "context_window": 1_000_000,
        "modalities": ["text", "image"],
        "latency": "medium",
    },
    "openai/gpt-4o": {
        "context_window": 128_000,
        "modalities": ["text", "image"],
        "latency": "medium",
    },
    "openai/gpt-4o-mini": {
        "context_window": 128_000,
        "modalities": ["text"],
        "latency": "low",
    },
}


def get_model_capabilities(provider: str, model: str) -> Dict[str, Any]:
    return MODEL_CAPABILITIES.get(f"{provider}/{model}", {})
