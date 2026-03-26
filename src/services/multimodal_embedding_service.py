"""Multimodal embedding service using Vertex AI multimodalembedding@001 REST API.

Generates 1408-dimensional embeddings for text AND images in the same vector space,
enabling cross-modal semantic search (e.g., text query retrieves relevant images).

Uses REST API directly to avoid SDK initialization hangs in Cloud Run.

References:
- https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-multimodal-embeddings
- https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/multimodal-embeddings-api
- Pricing: $0.00015/image, $0.000025/1K chars text (online)
"""
from __future__ import annotations

import base64
import io
import os
import time
import threading
from functools import lru_cache
from typing import List, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

import google.auth
import google.auth.transport.requests
import requests
import logging

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _shared_requests_session() -> requests.Session:
    return requests.Session()


_token_lock = threading.Lock()
_token_cache: dict = {"token": None, "expiry": 0.0, "creds": None}

try:
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None


class MultimodalEmbeddingService:
    """Compute multimodal embeddings using Vertex AI multimodalembedding@001 REST API.
    
    Key features:
    - 1408-dimensional vectors (vs 768 for text-only models)
    - Text and images embedded in the SAME vector space
    - Enables cross-modal search: text query can retrieve images and vice versa
    - Uses REST API directly to avoid SDK initialization hangs
    
    Limits:
    - Max text: 1024 tokens (~4096 chars)
    - Max image: 1024x1024 pixels (auto-resized if larger)
    - Supported image formats: PNG, JPEG, GIF, BMP, WEBP
    """

    MODEL_NAME = "multimodalembedding@001"
    DIMENSION = 1408
    MAX_TEXT_CHARS = 4096  # ~1024 tokens
    MAX_TEXT_TOKENS = 1024
    MAX_IMAGE_SIZE = 1024  # pixels on longest side

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required for MultimodalEmbeddingService")
        
        resolved_location = (
            location
            or os.getenv("VERTEX_MULTIMODAL_LOCATION")
            or os.getenv("VERTEX_AI_LOCATION", "us-central1")
        )
        # Multimodal embeddings require regional endpoint, not global
        if resolved_location == "global":
            resolved_location = "us-central1"
        self.location = resolved_location
        
        self._credentials = None
        self._token_expiry = 0

    def _get_access_token(self) -> str:
        """Get access token using ADC, refresh if expired."""
        now = time.time()
        with _token_lock:
            cached_token = _token_cache.get("token")
            cached_expiry = float(_token_cache.get("expiry") or 0.0)
            if cached_token and now < (cached_expiry - 60):
                return str(cached_token)

            creds = _token_cache.get("creds")
            if creds is None:
                creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
                _token_cache["creds"] = creds

            auth_req = google.auth.transport.requests.Request()
            creds.refresh(auth_req)
            expiry = creds.expiry.timestamp() if getattr(creds, "expiry", None) else now + 3600
            token = creds.token
            _token_cache["token"] = token
            _token_cache["expiry"] = expiry
            return str(token)

    def _get_api_url(self) -> str:
        """Build the REST API URL."""
        return (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self.MODEL_NAME}:predict"
        )

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    @staticmethod
    @lru_cache(maxsize=1)
    def _encoder():
        if tiktoken is None:
            raise RuntimeError("tiktoken is required for token truncation")
        return tiktoken.get_encoding("cl100k_base")

    def _truncate_text(self, text: str) -> str:
        if not text:
            return ""
        enc = self._encoder()
        toks = enc.encode(text)
        if len(toks) > self.MAX_TEXT_TOKENS:
            text = enc.decode(toks[: self.MAX_TEXT_TOKENS])
            logger.warning(f"Text truncated to {self.MAX_TEXT_TOKENS} tokens for embedding")
        if len(text) > self.MAX_TEXT_CHARS:
            text = text[: self.MAX_TEXT_CHARS]
            logger.warning(f"Text truncated to {self.MAX_TEXT_CHARS} chars for embedding")
        return text

    @retry(
        retry=retry_if_exception_type(requests.exceptions.HTTPError),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True
    )
    def _post_with_retry(self, session, url, json, headers, timeout):
        resp = session.post(url, json=json, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            # Raise generic HTTPError to trigger retry
            resp.raise_for_status()
        return resp

    def embed_text(self, text: str, contextual_text: Optional[str] = None) -> List[float]:
        """Embed a single text string.
        
        Args:
            text: The text to embed (max ~4096 chars / 1024 tokens)
            contextual_text: Optional additional context (unused, for API compat)
            
        Returns:
            1408-dimensional embedding vector
        """
        _t0 = time.time()
        logger.info(f"[PERF] embed_text START: {len(text)} chars")
        
        if not text:
            return [0.0] * self.DIMENSION
        
        # Truncate deterministically by tokens first (Vertex limit), then by chars (safety).
        text = self._truncate_text(text)
        
        timeout_s = float(os.getenv("VERTEX_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "30") or "30")
        
        try:
            token = self._get_access_token()
        except Exception as e:
            logger.error(f"[PERF] embed_text: failed to get access token: {e}")
            return [0.0] * self.DIMENSION
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        session = _shared_requests_session()
        body = {"instances": [{"text": text, "parameters": {"dimension": self.DIMENSION}}]}
        
        try:
            # Use internal retry helper logic manually or via tenacity if refactored
            # Here we implement a simple loop for 429 specifically to avoid major refactors
            for attempt in range(5):
                try:
                    resp = session.post(self._get_api_url(), json=body, headers=headers, timeout=timeout_s)
                    
                    if resp.status_code == 429:
                        sleep_time = (2 ** attempt) + (2.0 * (time.time() % 1)) # More aggressive Jitter
                        logger.warning(f"Rate limited (429) on {self.MODEL_NAME}, retrying in {sleep_time:.2f}s (attempt {attempt+1}/5)...")
                        time.sleep(sleep_time)
                        continue
                        
                    if resp.status_code == 400:
                        logger.error(f"[PERF] embed_text 400 response: {resp.text[:2000]}")
                        # Fallbacks...
                        fallback_body = {"instances": [{"text": text}]}
                        resp = session.post(self._get_api_url(), json=fallback_body, headers=headers, timeout=timeout_s)
                        
                    resp.raise_for_status()
                    data = resp.json()
                    
                    predictions = data.get("predictions", [])
                    if predictions:
                        text_embedding = predictions[0].get("textEmbedding", [])
                        if text_embedding and len(text_embedding) == self.DIMENSION:
                            logger.info(f"[PERF] embed_text DONE: {(time.time() - _t0)*1000:.0f}ms")
                            return text_embedding
                    
                    break # Success but no/invalid prediction
                    
                except requests.exceptions.RequestException as re:
                     # Only retry specific errors if needed, but here we handled 429 explicitly
                     if attempt == 4:
                         raise
            
            logger.warning("[PERF] embed_text: no valid embedding in response")
            return [0.0] * self.DIMENSION
            
        except requests.exceptions.Timeout:
            logger.error(f"[PERF] embed_text TIMEOUT after {timeout_s}s")
            return [0.0] * self.DIMENSION
        except Exception as e:
            logger.error(f"[PERF] embed_text FAILED after {(time.time() - _t0)*1000:.0f}ms: {e}")
            return [0.0] * self.DIMENSION

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple text strings.

        Uses a single REST call with multiple instances (chunked) to reduce
        network overhead.
        """
        if not texts:
            return []

        timeout_s = float(os.getenv("VERTEX_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "30") or "30")
        try:
            max_batch = int(os.getenv("VERTEX_EMBEDDING_MAX_BATCH_SIZE", "64") or "64")
        except Exception:
            max_batch = 64
        max_batch = max(1, min(256, max_batch))

        try:
            token = self._get_access_token()
        except Exception as e:
            logger.error(f"[PERF] embed_texts: failed to get access token: {e}")
            return [[0.0] * self.DIMENSION for _ in texts]

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        session = _shared_requests_session()

        out: List[List[float]] = []
        for i in range(0, len(texts), max_batch):
            chunk = texts[i : i + max_batch]
            instances = []
            for t in chunk:
                tt = self._truncate_text(t or "")
                instances.append({"text": tt, "parameters": {"dimension": self.DIMENSION}})

            body = {"instances": instances}

            try:
                resp = session.post(self._get_api_url(), json=body, headers=headers, timeout=timeout_s)
                if resp.status_code == 400:
                    # Some model endpoints may reject multi-instance payloads.
                    logger.error(f"[PERF] embed_texts 400 response: {resp.text[:2000]}")
                    raise ValueError("batch_embedding_unsupported")
                resp.raise_for_status()
                data = resp.json() or {}
                predictions = data.get("predictions", []) or []

                # Defensive: ensure length matches.
                if len(predictions) != len(chunk):
                    logger.error(
                        f"[PERF] embed_texts: predictions length mismatch: got={len(predictions)} expected={len(chunk)}"
                    )
                    raise ValueError("prediction_length_mismatch")

                for pred in predictions:
                    vec = pred.get("textEmbedding", []) if isinstance(pred, dict) else []
                    if vec and len(vec) == self.DIMENSION:
                        out.append(vec)
                    else:
                        out.append([0.0] * self.DIMENSION)

            except Exception as e:
                # Correctness > speed: fall back to single-item calls.
                logger.warning(f"[PERF] embed_texts batch failed, falling back to per-item: {e}")
                for t in chunk:
                    out.append(self.embed_text(t or ""))

        return out

    def embed_image(
        self,
        image_bytes: bytes,
        contextual_text: Optional[str] = None,
    ) -> List[float]:
        """Embed an image.
        
        Args:
            image_bytes: Raw image bytes (PNG, JPEG, GIF, BMP, WEBP)
            contextual_text: Optional text context to pair with image
            
        Returns:
            1408-dimensional embedding vector (same space as text embeddings)
        """
        _t0 = time.time()
        logger.info(f"[PERF] embed_image START: {len(image_bytes)} bytes")
        
        if not image_bytes:
            return [0.0] * self.DIMENSION
        
        # Resize if needed
        resized_bytes = self._resize_image_if_needed(image_bytes)
        
        timeout_s = float(os.getenv("VERTEX_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "60") or "60")
        
        try:
            token = self._get_access_token()
        except Exception as e:
            logger.error(f"[PERF] embed_image: failed to get access token: {e}")
            return [0.0] * self.DIMENSION
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        session = _shared_requests_session()
        
        # Build request body for image embedding
        instance: dict = {
            "image": {
                "bytesBase64Encoded": base64.b64encode(resized_bytes).decode("utf-8")
            },
            "parameters": {"dimension": self.DIMENSION}
        }
        if contextual_text:
            instance["text"] = contextual_text[: self.MAX_TEXT_CHARS]
        
        body = {"instances": [instance]}
        
        try:
            resp = session.post(self._get_api_url(), json=body, headers=headers, timeout=timeout_s)
            if resp.status_code == 400:
                logger.error(f"[PERF] embed_image 400 response: {resp.text[:2000]}")
            resp.raise_for_status()
            data = resp.json()
            
            predictions = data.get("predictions", [])
            if predictions:
                image_embedding = predictions[0].get("imageEmbedding", [])
                if image_embedding and len(image_embedding) == self.DIMENSION:
                    logger.info(f"[PERF] embed_image DONE: {(time.time() - _t0)*1000:.0f}ms")
                    return image_embedding
            
            logger.warning("[PERF] embed_image: no valid embedding in response")
            return [0.0] * self.DIMENSION
            
        except requests.exceptions.Timeout:
            logger.error(f"[PERF] embed_image TIMEOUT after {timeout_s}s")
            return [0.0] * self.DIMENSION
        except Exception as e:
            logger.error(f"[PERF] embed_image FAILED after {(time.time() - _t0)*1000:.0f}ms: {e}")
            return [0.0] * self.DIMENSION

    def embed_image_and_text(
        self,
        image_bytes: bytes,
        text: str,
    ) -> tuple[List[float], List[float]]:
        """Embed both image and text in a single call.
        
        Returns:
            Tuple of (image_embedding, text_embedding), both 1408-D
        """
        _t0 = time.time()
        
        if not image_bytes and not text:
            return [0.0] * self.DIMENSION, [0.0] * self.DIMENSION
        
        timeout_s = float(os.getenv("VERTEX_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "60") or "60")
        
        try:
            token = self._get_access_token()
        except Exception as e:
            logger.error(f"[PERF] embed_image_and_text: failed to get access token: {e}")
            return [0.0] * self.DIMENSION, [0.0] * self.DIMENSION
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        session = _shared_requests_session()
        
        instance: dict = {"parameters": {"dimension": self.DIMENSION}}
        
        if image_bytes:
            resized_bytes = self._resize_image_if_needed(image_bytes)
            instance["image"] = {
                "bytesBase64Encoded": base64.b64encode(resized_bytes).decode("utf-8")
            }
        
        if text:
            instance["text"] = text[: self.MAX_TEXT_CHARS]
        
        body = {"instances": [instance]}
        
        try:
            resp = session.post(self._get_api_url(), json=body, headers=headers, timeout=timeout_s)
            if resp.status_code == 400:
                logger.error(f"[PERF] embed_image_and_text 400 response: {resp.text[:2000]}")
            resp.raise_for_status()
            data = resp.json()
            
            predictions = data.get("predictions", [])
            if predictions:
                pred = predictions[0]
                img_emb = pred.get("imageEmbedding", []) or [0.0] * self.DIMENSION
                txt_emb = pred.get("textEmbedding", []) or [0.0] * self.DIMENSION
                
                if len(img_emb) != self.DIMENSION:
                    img_emb = [0.0] * self.DIMENSION
                if len(txt_emb) != self.DIMENSION:
                    txt_emb = [0.0] * self.DIMENSION
                
                logger.info(f"[PERF] embed_image_and_text DONE: {(time.time() - _t0)*1000:.0f}ms")
                return img_emb, txt_emb
            
            return [0.0] * self.DIMENSION, [0.0] * self.DIMENSION
            
        except requests.exceptions.Timeout:
            logger.error(f"[PERF] embed_image_and_text TIMEOUT after {timeout_s}s")
            return [0.0] * self.DIMENSION, [0.0] * self.DIMENSION
        except Exception as e:
            logger.error(f"[PERF] embed_image_and_text FAILED: {e}")
            return [0.0] * self.DIMENSION, [0.0] * self.DIMENSION

    def _resize_image_if_needed(self, image_bytes: bytes) -> bytes:
        """Resize image to max 1024px on longest side if needed."""
        try:
            from PIL import Image as PILImage
            
            img = PILImage.open(io.BytesIO(image_bytes))
            
            # Check if resize needed
            max_dim = max(img.width, img.height)
            if max_dim <= self.MAX_IMAGE_SIZE:
                return image_bytes
            
            # Calculate new size maintaining aspect ratio
            ratio = self.MAX_IMAGE_SIZE / max_dim
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, PILImage.LANCZOS)
            
            # Convert to RGB if needed (remove alpha channel)
            if img.mode in ("RGBA", "P", "LA"):
                background = PILImage.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            
            # Save to bytes
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()
            
        except Exception as e:
            logger.warning(f"Failed to resize image, using original: {e}")
            return image_bytes

    def embed_gcs_image(
        self,
        gcs_uri: str,
        contextual_text: Optional[str] = None,
    ) -> List[float]:
        """Embed an image directly from GCS URI.
        
        Args:
            gcs_uri: GCS path like gs://bucket/path/image.png
            contextual_text: Optional text context
            
        Returns:
            1408-dimensional embedding vector
        """
        _t0 = time.time()
        logger.info(f"[PERF] embed_gcs_image START: {gcs_uri}")
        
        timeout_s = float(os.getenv("VERTEX_EMBEDDING_REQUEST_TIMEOUT_SECONDS", "60") or "60")
        
        try:
            token = self._get_access_token()
        except Exception as e:
            logger.error(f"[PERF] embed_gcs_image: failed to get access token: {e}")
            return [0.0] * self.DIMENSION
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        # Build request body using gcsUri instead of base64
        instance: dict = {
            "image": {"gcsUri": gcs_uri},
            "parameters": {"dimension": self.DIMENSION}
        }
        if contextual_text:
            instance["text"] = contextual_text[: self.MAX_TEXT_CHARS]
        
        body = {"instances": [instance]}
        
        try:
            resp = requests.post(self._get_api_url(), json=body, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            
            predictions = data.get("predictions", [])
            if predictions:
                image_embedding = predictions[0].get("imageEmbedding", [])
                if image_embedding and len(image_embedding) == self.DIMENSION:
                    logger.info(f"[PERF] embed_gcs_image DONE: {(time.time() - _t0)*1000:.0f}ms")
                    return image_embedding
            
            logger.warning("[PERF] embed_gcs_image: no valid embedding in response")
            return [0.0] * self.DIMENSION
            
        except requests.exceptions.Timeout:
            logger.error(f"[PERF] embed_gcs_image TIMEOUT after {timeout_s}s: {gcs_uri}")
            return [0.0] * self.DIMENSION
        except Exception as e:
            logger.error(f"[PERF] embed_gcs_image FAILED: {e}")
            return [0.0] * self.DIMENSION
