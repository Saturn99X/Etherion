"""
Gemini 2.5 Flash Image client (aka "Nano Banana")

Reimplemented to use Vertex AI GenerativeModel (gemini-2.5-flash-image-preview)
so it matches the production ImageGeneratorTool stack.

Notes:
- No API key required; uses Vertex AI with project/region from env.
- For full asset persistence and BigQuery indexing, prefer
  `src/services/image_generation/service.py` which leverages
  `ImageGeneratorTool`.
"""

from __future__ import annotations

import base64
import os
import time
from typing import List, Optional, Tuple, Dict, Any

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part


class GeminiImageClient:
    def __init__(
        self,
        model_name: str = "gemini-2.5-flash-image",
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is not configured")
        self.location = location
        vertexai.init(project=self.project_id, location=self.location)
        self.model = GenerativeModel(model_name=model_name)

    @staticmethod
    def _to_parts(prompt: str, images: Optional[List[Tuple[str, bytes]]]) -> List[Any]:
        parts: List[Any] = [Part.from_text(prompt)]
        if images:
            for mime, raw in images:
                parts.append(Part.from_data(data=raw, mime_type=mime or "image/png"))
        return parts

    def generate(
        self,
        prompt: str,
        images: Optional[List[Tuple[str, bytes]]] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        safety_settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = GenerationConfig(
            response_modalities=["TEXT", "IMAGE"],
            **(generation_config or {}),
        )
        parts = self._to_parts(prompt, images)
        start = time.monotonic()
        resp = self.model.generate_content(parts, generation_config=config)
        duration_s = time.monotonic() - start

        # Extract inline image data (base64) from response
        image_outputs: List[Dict[str, Any]] = []
        candidates = getattr(resp, "candidates", []) or []
        for c in candidates:
            content = getattr(c, "content", None)
            if not content:
                continue
            for p in getattr(content, "parts", []) or []:
                inline = getattr(p, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    # inline.data is already base64-encoded bytes
                    data_b64 = inline.data
                    # Some SDKs return bytes; ensure str
                    if isinstance(data_b64, (bytes, bytearray)):
                        data_b64 = data_b64.decode("utf-8")
                    image_outputs.append({
                        "mime_type": getattr(inline, "mime_type", "image/png"),
                        "data_base64": data_b64,
                    })

        return {
            "duration_seconds": duration_s,
            "images": image_outputs,
            "safety": None,
            "safety_ratings": None,
        }


