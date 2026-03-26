from __future__ import annotations

from typing import List, Any
import os
import logging
import time

import google.auth
import google.auth.transport.requests
import requests

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Compute text embeddings using Vertex AI REST API directly (no SDK).

    Uses REST API to avoid SDK initialization hangs in Cloud Run.
    Default model: text-embedding-005 (768-d).
    """

    def __init__(self, project_id: str | None = None, location: str | None = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required for EmbeddingService")
        resolved_location = (
            location
            or os.getenv("VERTEX_EMBEDDING_LOCATION")
            or os.getenv("VERTEX_AI_LOCATION", "us-central1")
        )
        if resolved_location == "global":
            resolved_location = "us-central1"
        self.location = resolved_location
        self._model_name = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-005")
        self._dim = 768
        self._credentials = None
        self._token_expiry = 0

    def _get_access_token(self) -> str:
        """Get access token using ADC, refresh if expired."""
        now = time.time()
        if self._credentials is None or now >= self._token_expiry - 60:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            auth_req = google.auth.transport.requests.Request()
            self._credentials.refresh(auth_req)
            self._token_expiry = self._credentials.expiry.timestamp() if self._credentials.expiry else now + 3600
        return self._credentials.token

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_texts(self, texts: List[str], task: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """Embed texts using Vertex AI REST API directly."""
        if not texts:
            return []
        
        _t0 = time.time()
        logger.info(f"[PERF] EmbeddingService.embed_texts START: {len(texts)} texts")
        
        timeout_s = float(os.getenv("VERTEX_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "30") or "30")
        
        # Build REST API URL
        url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self._model_name}:predict"
        )
        
        # Get access token
        try:
            token = self._get_access_token()
        except Exception as e:
            logger.error(f"[PERF] EmbeddingService: failed to get access token: {e}")
            return [[0.0] * self._dim for _ in texts]
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        # Batch texts (API limit is 5 texts per request for most models)
        batch_size = min(5, int(os.getenv("VERTEX_EMBEDDING_BATCH_SIZE", "5") or "5"))
        out: List[List[float]] = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            
            # Build request body
            body = {
                "instances": [{"content": t} for t in batch],
            }
            
            try:
                resp = requests.post(url, json=body, headers=headers, timeout=timeout_s)
                resp.raise_for_status()
                data = resp.json()
                
                predictions = data.get("predictions", [])
                for pred in predictions:
                    embeddings = pred.get("embeddings", {})
                    values = embeddings.get("values", [])
                    if values and len(values) == self._dim:
                        out.append(values)
                    else:
                        out.append([0.0] * self._dim)
                        
            except requests.exceptions.Timeout:
                logger.error(f"[PERF] EmbeddingService: request timed out after {timeout_s}s")
                out.extend([[0.0] * self._dim for _ in batch])
            except Exception as e:
                logger.error(f"[PERF] EmbeddingService: request failed: {e}")
                out.extend([[0.0] * self._dim for _ in batch])
        
        logger.info(f"[PERF] EmbeddingService.embed_texts DONE: {len(out)} vectors in {(time.time() - _t0)*1000:.0f}ms")
        return out
