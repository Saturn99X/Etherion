"""Unit tests for MultimodalEmbeddingService."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestMultimodalEmbeddingService:
    """Test multimodal embedding service configuration and methods."""

    def test_dimension_is_1408(self):
        """Multimodal embeddings must be 1408-D."""
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        assert MultimodalEmbeddingService.DIMENSION == 1408

    def test_model_name_is_multimodalembedding001(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        assert MultimodalEmbeddingService.MODEL_NAME == "multimodalembedding@001"

    def test_max_text_chars_limit(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        # 1024 tokens * 4 chars/token = 4096 chars
        assert MultimodalEmbeddingService.MAX_TEXT_CHARS == 4096

    def test_max_image_size_is_1024(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        assert MultimodalEmbeddingService.MAX_IMAGE_SIZE == 1024

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_init_with_project(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        svc = MultimodalEmbeddingService()
        assert svc.project_id == "test-project"
        assert svc.dimension == 1408

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_embed_text_empty_returns_zeros(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        svc = MultimodalEmbeddingService()
        result = svc.embed_text("")

        assert len(result) == 1408
        assert all(v == 0.0 for v in result)

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_embed_image_empty_returns_zeros(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        svc = MultimodalEmbeddingService()
        result = svc.embed_image(b"")

        assert len(result) == 1408
        assert all(v == 0.0 for v in result)

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_location_normalization_global_to_us_central1(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService

        svc = MultimodalEmbeddingService(location="global")
        assert svc.location == "us-central1"


class TestImageResizing:
    """Test image preprocessing for embedding."""

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_small_image_not_resized(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService
        from PIL import Image
        import io

        svc = MultimodalEmbeddingService()

        # Create small 100x100 image
        img = Image.new("RGB", (100, 100), color="red")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        original_bytes = buffer.getvalue()

        result = svc._resize_image_if_needed(original_bytes)

        # Should return same bytes (not resized)
        assert result == original_bytes

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_large_image_resized(self):
        from src.services.multimodal_embedding_service import MultimodalEmbeddingService
        from PIL import Image
        import io

        svc = MultimodalEmbeddingService()

        # Create large 2048x2048 image
        img = Image.new("RGB", (2048, 2048), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        original_bytes = buffer.getvalue()

        result = svc._resize_image_if_needed(original_bytes)

        # Verify resized
        resized_img = Image.open(io.BytesIO(result))
        assert max(resized_img.width, resized_img.height) <= 1024
