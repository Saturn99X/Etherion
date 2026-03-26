"""Unit tests for MultimodalSearchService."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestMultimodalSearchResult:
    """Test search result dataclass."""

    def test_doc_result(self):
        from src.services.multimodal_search_service import MultimodalSearchResult

        result = MultimodalSearchResult(
            result_type="doc",
            id="doc-123",
            gcs_uri="gs://bucket/file.pdf",
            distance=0.15,
            filename="report.pdf",
            part_number=1,
            total_parts=2,
            essence_text="Chapter 1: Introduction",
        )

        assert result.result_type == "doc"
        assert result.distance == 0.15
        assert result.part_number == 1

    def test_image_result(self):
        from src.services.multimodal_search_service import MultimodalSearchResult

        result = MultimodalSearchResult(
            result_type="image",
            id="img-456",
            gcs_uri="gs://bucket/images/chart.png",
            distance=0.22,
            chapter_heading="Revenue Analysis",
        )

        assert result.result_type == "image"
        assert result.chapter_heading == "Revenue Analysis"


class TestMultimodalSearchServiceInit:
    """Test service initialization."""

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    @patch("src.services.multimodal_search_service.BigQueryService")
    def test_init_with_project(self, mock_bqs):
        from src.services.multimodal_search_service import MultimodalSearchService

        svc = MultimodalSearchService()
        assert svc.project_id == "test-project"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_without_project_raises(self):
        from src.services.multimodal_search_service import MultimodalSearchService

        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT is required"):
            MultimodalSearchService()


class TestMultimodalSearchServiceHelpers:
    """Test helper functions."""

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    def test_fetch_gcs_content(self):
        from src.services.multimodal_search_service import fetch_gcs_content
        from unittest.mock import patch

        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"file content"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_client):
            result = fetch_gcs_content("gs://my-bucket/path/to/file.pdf")

        assert result == b"file content"
        mock_client.bucket.assert_called_with("my-bucket")
        mock_bucket.blob.assert_called_with("path/to/file.pdf")


class TestSearchResultSorting:
    """Test that results are sorted by distance."""

    def test_results_sorted_by_distance(self):
        from src.services.multimodal_search_service import MultimodalSearchResult

        results = [
            MultimodalSearchResult(result_type="doc", id="a", gcs_uri="", distance=0.5),
            MultimodalSearchResult(result_type="image", id="b", gcs_uri="", distance=0.1),
            MultimodalSearchResult(result_type="doc", id="c", gcs_uri="", distance=0.3),
        ]

        sorted_results = sorted(results, key=lambda r: r.distance)

        assert sorted_results[0].id == "b"  # distance 0.1
        assert sorted_results[1].id == "c"  # distance 0.3
        assert sorted_results[2].id == "a"  # distance 0.5
