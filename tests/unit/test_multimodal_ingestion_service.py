"""Unit tests for MultimodalIngestionService."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


def _make_pdf_bytes(pages: list[str]) -> bytes:
    import io
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, text in enumerate(pages):
        c.drawString(72, 720, text)
        if i < len(pages) - 1:
            c.showPage()
    c.save()
    return buf.getvalue()


class TestMultimodalIngestionResult:
    """Test result dataclass."""

    def test_result_fields(self):
        from src.services.multimodal_ingestion_service import MultimodalIngestionResult

        result = MultimodalIngestionResult(
            tenant_id="123",
            gcs_uri="gs://bucket/file.pdf",
            filename="file.pdf",
            mime_type="application/pdf",
            size_bytes=1000,
            doc_ids=["doc-1", "doc-2"],
            image_ids=["img-1"],
            chapter_count=5,
            part_count=2,
            total_tokens=50000,
            job_id="job-123",
            errors=[],
        )

        assert result.tenant_id == "123"
        assert len(result.doc_ids) == 2
        assert result.part_count == 2
        assert result.total_tokens == 50000


class TestMultimodalIngestionServiceInit:
    """Test service initialization."""

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    @patch("src.services.multimodal_ingestion_service.storage")
    @patch("src.services.multimodal_ingestion_service.bigquery")
    def test_init_with_project(self, mock_bq, mock_storage):
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        svc = MultimodalIngestionService()
        assert svc.project_id == "test-project"
        mock_storage.Client.assert_not_called()
        mock_bq.Client.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    def test_init_without_project_raises(self):
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT is required"):
            MultimodalIngestionService()


class TestMultimodalIngestionServiceHelpers:
    """Test helper methods."""

    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project", "GCS_BUCKET_PREFIX": "tnt"})
    @patch("src.services.multimodal_ingestion_service.storage")
    @patch("src.services.multimodal_ingestion_service.bigquery")
    def test_tenant_bucket_naming(self, mock_bq, mock_storage):
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        mock_storage.Client.return_value = MagicMock()
        svc = MultimodalIngestionService()

        bucket = svc._tenant_bucket("tenant-123", "media")
        mock_storage.Client.return_value.bucket.assert_called_with("tnt-tenant-123-media")


class TestMultimodalIngestionServiceTextFallback:
    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"})
    @patch("src.services.multimodal_ingestion_service.ensure_tenant_multimodal_kb")
    @patch("src.services.multimodal_ingestion_service.storage")
    @patch("src.services.multimodal_ingestion_service.bigquery")
    def test_text_plain_does_not_use_docling(self, mock_bq, mock_storage, mock_ensure_kb):
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        svc = MultimodalIngestionService()
        mock_ensure_kb.return_value = None

        bq_client = MagicMock()
        bq_client.insert_rows_json.return_value = []

        embedder = MagicMock()
        embedder.embed_text.return_value = [0.0] * 1408
        embedder.DIMENSION = 1408

        with patch.object(MultimodalIngestionService, "bq", new_callable=PropertyMock, return_value=bq_client):
            with patch.object(MultimodalIngestionService, "embedder", new_callable=PropertyMock, return_value=embedder):
                with patch.object(MultimodalIngestionService, "docling", new_callable=PropertyMock, side_effect=AssertionError("docling should not be accessed")):
                    result = svc._ingest_with_content(
                        tenant_id="123",
                        gcs_uri="gs://bucket/foo.txt",
                        content=b"hello world",
                        filename="foo.txt",
                        mime_type="text/plain",
                        size_bytes=11,
                        project_id=None,
                        job_id="job-1",
                        progress=None,
                    )

        assert result.chapter_count == 1
        assert result.doc_ids


class TestMultimodalIngestionServiceConstants:
    """Test service constants."""

    def test_max_tokens_per_part(self):
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        assert MultimodalIngestionService.MAX_TOKENS_PER_PART == 300_000


class TestMultimodalIngestionServicePdfStreaming:
    @patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": "test-project"}, clear=True)
    @patch("src.services.multimodal_ingestion_service.storage")
    @patch("src.services.multimodal_ingestion_service.bigquery")
    def test_pdf_streaming_flushes_multiple_parts_and_inserts_rows(self, mock_bq, mock_storage):
        from src.services.multimodal_ingestion_service import MultimodalIngestionService

        storage_client = MagicMock()
        mock_storage.Client.return_value = storage_client

        bucket = MagicMock()
        bucket.name = "tnt-123-media"
        storage_client.bucket.return_value = bucket

        blob = MagicMock()
        bucket.blob.return_value = blob

        bq_client = MagicMock()
        bq_client.insert_rows_json.return_value = []
        bq_client.query.return_value = MagicMock(result=MagicMock(return_value=None))
        mock_bq.Client.return_value = bq_client
        mock_bq.QueryJobConfig.return_value = MagicMock()
        mock_bq.ScalarQueryParameter.return_value = MagicMock()
        mock_bq.ArrayQueryParameter.return_value = MagicMock()

        embedder = MagicMock()
        embedder.embed_texts.side_effect = lambda xs: [[0.0] * 1408 for _ in xs]
        embedder.embed_image.return_value = [0.0] * 1408
        embedder.DIMENSION = 1408

        svc = MultimodalIngestionService()
        svc.MAX_TOKENS_PER_PART = 20

        pdf_bytes = _make_pdf_bytes([
            "word " * 15,
            "word " * 15,
            "word " * 15,
        ])

        with patch.object(MultimodalIngestionService, "embedder", new_callable=PropertyMock, return_value=embedder):
            result = svc._ingest_pdf_streaming(
                tenant_id="123",
                gcs_uri="gs://tnt-123-media/uploads/abc/file.pdf",
                content=pdf_bytes,
                filename="file.pdf",
                mime_type="application/pdf",
                size_bytes=len(pdf_bytes),
                project_id=None,
                job_id="job-1",
                progress=None,
            )

        assert result.part_count == 3
        assert result.chapter_count == 3
        assert len(result.doc_ids) == 3

        assert bucket.blob.call_count == 3
        obj0 = bucket.blob.call_args_list[0].args[0]
        obj1 = bucket.blob.call_args_list[1].args[0]
        obj2 = bucket.blob.call_args_list[2].args[0]
        assert obj0.endswith("/parts/file_001.pdf")
        assert obj1.endswith("/parts/file_002.pdf")
        assert obj2.endswith("/parts/file_003.pdf")

        assert bq_client.insert_rows_json.call_count == 3
        rows0 = bq_client.insert_rows_json.call_args_list[0].args[1]
        rows1 = bq_client.insert_rows_json.call_args_list[1].args[1]
        rows2 = bq_client.insert_rows_json.call_args_list[2].args[1]
        assert rows0[0]["part_number"] == 1
        assert rows1[0]["part_number"] == 2
        assert rows2[0]["part_number"] == 3
        assert rows0[0]["part_name"] == "file_001.pdf"
        assert rows1[0]["part_name"] == "file_002.pdf"
        assert rows2[0]["part_name"] == "file_003.pdf"
        assert rows0[0]["mime_type"] == "application/pdf"
        assert rows1[0]["mime_type"] == "application/pdf"
        assert rows2[0]["mime_type"] == "application/pdf"

        bq_client.query.assert_called_once()

        assert embedder.embed_texts.call_count == 3
        for call in embedder.embed_texts.call_args_list:
            batch = call.args[0]
            assert isinstance(batch, list)
            assert len(batch) == 1
            assert "page" not in (batch[0] or "").lower()
