# src/utils/llm_providers/vertex.py
from __future__ import annotations
import os
from typing import Any, Dict

from .base import LLMProvider


class VertexProvider(LLMProvider):
    """Google Vertex AI (Gemini) provider using Service Account credentials only.

    Lazy-imports langchain_google_vertexai.ChatVertexAI to avoid hard deps when unused.
    """

    def load(self, *, model: str, config: Dict[str, Any]) -> Any:
        # Allow ADC (Application Default Credentials) on Cloud Run
        # We do not enforce GOOGLE_APPLICATION_CREDENTIALS file existence here.
        # credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise RuntimeError("VertexAI requires GOOGLE_CLOUD_PROJECT to be set.")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", os.getenv("VERTEX_AI_LOCATION", "us-central1"))

        try:
            from langchain_google_vertexai import ChatVertexAI
        except Exception as e:
            raise RuntimeError(
                "langchain_google_vertexai is required for Vertex models. Install it and retry."
            ) from e

        # Allow per-call overrides via config
        model_name = config.get("model_name", model)
        project = config.get("project", project_id)
        loc = config.get("location", location)

        kwargs: Dict[str, Any] = {
            "model_name": model_name,
            "project": project,
            "location": loc,
            "max_retries": 0,  # Disable LangChain retries - we handle retries in specialist_retry.py
            "timeout": 60,     # Set reasonable timeout (seconds)
        }
        if "temperature" in config:
            try:
                kwargs["temperature"] = float(config.get("temperature"))
            except Exception:
                pass
        if "max_output_tokens" in config:
            try:
                kwargs["max_output_tokens"] = int(config.get("max_output_tokens"))
            except Exception:
                pass
        if "timeout" in config:
            try:
                kwargs["timeout"] = int(config.get("timeout"))
            except Exception:
                pass
        # Allow override of max_retries if explicitly specified
        if "max_retries" in config:
            try:
                kwargs["max_retries"] = int(config.get("max_retries"))
            except Exception:
                pass

        try:
            llm = ChatVertexAI(**kwargs)
        except TypeError:
            llm = ChatVertexAI(model_name=model_name, project=project, location=loc)
        # Annotate with provider/model metadata so callers can report accurately
        try:
            setattr(llm, "provider", "vertex")
            setattr(llm, "model_name", model_name)
        except Exception:
            # Best-effort; do not fail construction if attributes cannot be set
            pass

        # Optional smoke test if requested
        if config.get("probe", False):
            llm.invoke("ping")
        return llm
