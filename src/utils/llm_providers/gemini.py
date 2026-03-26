"""Gemini LLM provider — supports both API key and Vertex AI ADC."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .base import LLMProvider, ProviderSpec

_DEFAULT_MODELS = {
    "default": "gemini-2.0-flash-001",
    "fast": "gemini-2.0-flash-lite-001",
    "smart": "gemini-2.5-pro-preview-05-06",
}


class GeminiProvider(LLMProvider):
    spec = ProviderSpec(
        name="gemini",
        display_name="Google Gemini",
        required_env=(),
        optional_env=("GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT"),
    )

    def load(self, model: str = "default", config: Optional[Dict[str, Any]] = None):
        model_id = _DEFAULT_MODELS.get(model, model)
        api_key = os.getenv("GEMINI_API_KEY")

        if api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model_id, google_api_key=api_key, **(config or {}))
        else:
            # Fall back to Vertex AI ADC
            from langchain_google_vertexai import ChatVertexAI
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
            return ChatVertexAI(model_name=model_id, project=project, location=location, **(config or {}))

    def is_available(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_CLOUD_PROJECT"))
