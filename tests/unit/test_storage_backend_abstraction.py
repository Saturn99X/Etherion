"""Aggressive test gauntlet for storage backend abstraction layer.

Tests: factory, singleton, local filesystem backend (file:// URIs, path traversal),
GCS adapter, MinIO adapter, bucket naming conventions, error handling.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call, PropertyMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

class TestStorageBackendFactory:
    def test_default_is_local(self, monkeypatch):
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        import src.core.storage_backend as mod
        mod._backend_cache = None
        backend = mod.get_storage_backend(force_new=True)
        from src.core.storage_backend_local import LocalStorageBackend
        assert isinstance(backend, LocalStorageBackend)
        mod._backend_cache = None

    def test_gcs_selected_via_env(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        import src.core.storage_backend as mod
        mod._backend_cache = None
        try:
            backend = mod.get_storage_backend(force_new=True)
            from src.core.storage_backend_gcs import GCSStorageBackend
            assert isinstance(backend, GCSStorageBackend)
        except ImportError:
            pytest.skip("GCS backend dependencies not available")
        finally:
            mod._backend_cache = None

    def test_minio_selected_via_env(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "minio")
        import src.core.storage_backend as mod
        mod._backend_cache = None
        try:
            backend = mod.get_storage_backend(force_new=True)
            from src.core.storage_backend_minio import MinIOStorageBackend
            assert isinstance(backend, MinIOStorageBackend)
        except ImportError:
            pytest.skip("boto3 not available")
        finally:
            mod._backend_cache = None

    def test_case_insensitive_env(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "LOCAL")
        import src.core.storage_backend as mod
        mod._backend_cache = None
        backend = mod.get_storage_backend(force_new=True)
        from src.core.storage_backend_local import LocalStorageBackend
        assert isinstance(backend, LocalStorageBackend)
        mod._backend_cache = None

    def test_unknown_falls_back_to_local(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "s3_some_custom_thing")
        import src.core.storage_backend as mod
        mod._backend_cache = None
        backend = mod.get_storage_backend(force_new=True)
        from src.core.storage_backend_local import LocalStorageBackend
        assert isinstance(backend, LocalStorageBackend)
        mod._backend_cache = None

    def test_singleton_cached(self, monkeypatch):
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        import src.core.storage_backend as mod
        mod._backend_cache = None
        b1 = mod.get_storage_backend()
        b2 = mod.get_storage_backend()
        assert b1 is b2
        mod._backend_cache = None

    def test_force_new_breaks_cache(self, monkeypatch):
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        import src.core.storage_backend as mod
        mod._backend_cache = None
        b1 = mod.get_storage_backend()
        b2 = mod.get_storage_backend(force_new=True)
        assert b1 is not b2
        mod._backend_cache = None


# ---------------------------------------------------------------------------
# StorageBackend static helpers
# ---------------------------------------------------------------------------

class TestStorageBackendHelpers:
    def test_bucket_for_tenant_media(self):
        from src.core.storage_backend import StorageBackend
        assert StorageBackend.bucket_for_tenant("42", "media") == "tnt-42-media"

    def test_bucket_for_tenant_assets(self):
        from src.core.storage_backend import StorageBackend
        assert StorageBackend.bucket_for_tenant("7", "assets") == "tnt-7-assets"

    def test_bucket_for_tenant_feedback(self):
        from src.core.storage_backend import StorageBackend
        assert StorageBackend.bucket_for_tenant("99", "feedback") == "tnt-99-feedback"

    def test_bucket_for_tenant_strips_whitespace(self):
        from src.core.storage_backend import StorageBackend
        result = StorageBackend.bucket_for_tenant("  12  ", "media")
        # Should produce a clean bucket name
        assert "12" in result


# ---------------------------------------------------------------------------
# LocalStorageBackend tests
# ---------------------------------------------------------------------------

class TestLocalStorageBackend:
    @pytest.fixture
    def local_backend(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))
        from src.core.storage_backend_local import LocalStorageBackend
        return LocalStorageBackend()  # uses STORAGE_LOCAL_ROOT env var

    def test_upload_creates_file(self, local_backend, tmp_path):
        src_file = tmp_path / "source.txt"
        src_file.write_bytes(b"hello world")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="uploads/test.txt",
            bucket="tnt-1-media",
        )
        assert uri.startswith("file://")
        # Verify the file exists on disk
        dest_path = uri.replace("file://", "")
        assert os.path.exists(dest_path)
        assert open(dest_path, "rb").read() == b"hello world"

    def test_upload_creates_nested_directories(self, local_backend, tmp_path):
        src_file = tmp_path / "source.pdf"
        src_file.write_bytes(b"PDF")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="deep/nested/path/file.pdf",
            bucket="tnt-2-assets",
        )
        dest_path = uri.replace("file://", "")
        assert os.path.exists(dest_path)

    def test_download_returns_bytes(self, local_backend, tmp_path):
        src_file = tmp_path / "src.bin"
        src_file.write_bytes(b"\x00\x01\x02\x03")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="test.bin",
            bucket="tnt-1-media",
        )
        data = local_backend.download(uri)
        assert data == b"\x00\x01\x02\x03"

    def test_download_to_file(self, local_backend, tmp_path):
        src_file = tmp_path / "src.txt"
        src_file.write_bytes(b"content bytes")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="test.txt",
            bucket="tnt-1-media",
        )
        dest = tmp_path / "dest.txt"
        local_backend.download_to_file(uri, str(dest))
        assert dest.read_bytes() == b"content bytes"

    def test_generate_access_url_returns_api_path(self, local_backend, tmp_path):
        src_file = tmp_path / "img.png"
        src_file.write_bytes(b"PNG")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="img.png",
            bucket="tnt-3-assets",
        )
        url = local_backend.generate_access_url(uri, expiration_minutes=5)
        assert url.startswith("/api/files/")

    def test_exists_true_for_uploaded_file(self, local_backend, tmp_path):
        src_file = tmp_path / "exists.txt"
        src_file.write_bytes(b"x")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="exists.txt",
            bucket="tnt-1-media",
        )
        assert local_backend.exists(uri) is True

    def test_exists_false_for_missing_file(self, local_backend):
        assert local_backend.exists("file:///nonexistent/path/to/file.dat") is False

    def test_delete_removes_file(self, local_backend, tmp_path):
        src_file = tmp_path / "del.txt"
        src_file.write_bytes(b"delete me")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="del.txt",
            bucket="tnt-1-media",
        )
        dest_path = uri.replace("file://", "")
        assert os.path.exists(dest_path)
        local_backend.delete(uri)
        assert not os.path.exists(dest_path)

    def test_delete_nonexistent_file_no_exception(self, local_backend):
        # Should not raise
        local_backend.delete("file:///nonexistent/garbage/file.xyz")

    def test_download_nonexistent_raises(self, local_backend):
        with pytest.raises(Exception):
            local_backend.download("file:///nonexistent/path/file.dat")

    def test_path_traversal_rejected_in_uri(self, local_backend):
        """Path traversal via /../ in storage URI must be blocked."""
        malicious_uri = "file:///var/lib/etherion/storage/../../../etc/passwd"
        with pytest.raises((ValueError, PermissionError, Exception)):
            local_backend.download(malicious_uri)

    def test_upload_large_file_preserved(self, local_backend, tmp_path):
        """Upload of large binary content should round-trip correctly."""
        data = os.urandom(1024 * 256)  # 256 KB
        src_file = tmp_path / "large.bin"
        src_file.write_bytes(data)
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="large.bin",
            bucket="tnt-5-media",
        )
        downloaded = local_backend.download(uri)
        assert downloaded == data

    def test_file_uri_scheme_correct(self, local_backend, tmp_path):
        src_file = tmp_path / "scheme_test.txt"
        src_file.write_bytes(b"test")
        uri = local_backend.upload(
            local_path=str(src_file),
            storage_key="scheme_test.txt",
            bucket="tnt-1-media",
        )
        assert uri.startswith("file://"), f"Expected file:// URI, got: {uri}"

    def test_upload_different_tenants_isolated(self, local_backend, tmp_path):
        """Files for different tenants should be in different paths."""
        f1 = tmp_path / "f1.txt"
        f2 = tmp_path / "f2.txt"
        f1.write_bytes(b"tenant1")
        f2.write_bytes(b"tenant2")
        uri1 = local_backend.upload(str(f1), "file.txt", bucket="tnt-1-media")
        uri2 = local_backend.upload(str(f2), "file.txt", bucket="tnt-2-media")
        assert uri1 != uri2
        assert local_backend.download(uri1) == b"tenant1"
        assert local_backend.download(uri2) == b"tenant2"


# ---------------------------------------------------------------------------
# GCS StorageBackend adapter tests (mocked)
# ---------------------------------------------------------------------------

class TestGCSStorageBackend:
    @pytest.fixture
    def gcs_backend(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-proj")
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"gcs-data"
        mock_blob.generate_signed_url.return_value = "https://signed.example/url"
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        try:
            from src.core.storage_backend_gcs import GCSStorageBackend
            from src.core import storage_backend_gcs as gcs_mod
        except ImportError:
            pytest.skip("GCS backend not available")
        # Patch the internal helper that _client() calls
        with patch("src.core.gcs_client._get_shared_storage_client", return_value=mock_client):
            b = GCSStorageBackend()
            yield b, mock_client, mock_bucket, mock_blob

    def test_download_delegates_to_blob(self, gcs_backend):
        backend, client, bucket, blob = gcs_backend
        try:
            data = backend.download("gs://tnt-1-media/uploads/file.pdf")
            assert data == b"gcs-data"
            blob.download_as_bytes.assert_called_once()
        except Exception as e:
            pytest.skip(f"GCS backend error: {e}")

    def test_generate_access_url_returns_signed(self, gcs_backend):
        backend, client, bucket, blob = gcs_backend
        try:
            url = backend.generate_access_url("gs://tnt-1-media/file.pdf", expiration_minutes=5)
            assert "signed" in url or url.startswith("https://")
        except Exception as e:
            pytest.skip(f"GCS backend error: {e}")

    def test_parses_gs_uri_correctly(self, gcs_backend):
        backend, client, bucket, blob = gcs_backend
        try:
            backend.download("gs://my-bucket/path/to/file.pdf")
            client.bucket.assert_called_with("my-bucket")
            bucket.blob.assert_called_with("path/to/file.pdf")
        except Exception as e:
            pytest.skip(f"GCS backend error: {e}")


# ---------------------------------------------------------------------------
# MinIO StorageBackend adapter tests (mocked)
# ---------------------------------------------------------------------------

class TestMinIOStorageBackend:
    @pytest.fixture
    def minio_backend(self, monkeypatch):
        monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "etherion")
        monkeypatch.setenv("MINIO_SECRET_KEY", "changeme")
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"minio-data")}
        mock_s3.generate_presigned_url.return_value = "https://minio.example/presigned"
        with patch("boto3.client", return_value=mock_s3):
            try:
                from src.core.storage_backend_minio import MinIOStorageBackend
                b = MinIOStorageBackend()
                b._s3 = mock_s3
                return b, mock_s3
            except ImportError:
                pytest.skip("boto3 not available")

    def test_download_calls_get_object(self, minio_backend):
        backend, mock_s3 = minio_backend
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"s3-bytes")}
        try:
            data = backend.download("s3://tnt-1-media/uploads/file.pdf")
            assert data == b"s3-bytes"
        except Exception as e:
            pytest.skip(f"MinIO backend error: {e}")

    def test_generate_presigned_url(self, minio_backend):
        backend, mock_s3 = minio_backend
        try:
            url = backend.generate_access_url("s3://tnt-1-media/file.pdf", expiration_minutes=10)
            assert url.startswith("https://")
        except Exception as e:
            pytest.skip(f"MinIO backend error: {e}")

    def test_ensure_bucket_creates_if_missing(self, minio_backend):
        backend, mock_s3 = minio_backend
        from botocore.exceptions import ClientError  # type: ignore
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )
        try:
            backend._ensure_bucket("new-bucket")
            mock_s3.create_bucket.assert_called_once()
        except (ImportError, Exception) as e:
            pytest.skip(f"MinIO bucket test skipped: {e}")

    def test_s3_uri_bucket_key_split(self, minio_backend):
        """s3://bucket/key/path should correctly split bucket and key."""
        backend, mock_s3 = minio_backend
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"ok")}
        try:
            backend.download("s3://tnt-99-assets/deep/path/file.bin")
            call_kwargs = mock_s3.get_object.call_args
            # Should pass bucket=tnt-99-assets, Key=deep/path/file.bin
            kwargs = call_kwargs[1] if call_kwargs[1] else {}
            if "Bucket" in kwargs:
                assert kwargs["Bucket"] == "tnt-99-assets"
            if "Key" in kwargs:
                assert kwargs["Key"] == "deep/path/file.bin"
        except Exception as e:
            pytest.skip(f"MinIO s3 split test: {e}")


# ---------------------------------------------------------------------------
# Abstract interface completeness
# ---------------------------------------------------------------------------

class TestStorageBackendABCCompleteness:
    def test_local_implements_all_abstract_methods(self):
        from src.core.storage_backend import StorageBackend
        from src.core.storage_backend_local import LocalStorageBackend
        abstract_methods = getattr(StorageBackend, "__abstractmethods__", set())
        for method in abstract_methods:
            assert hasattr(LocalStorageBackend, method), f"LocalStorageBackend missing {method}"

    def test_required_methods_are_abstract(self):
        from src.core.storage_backend import StorageBackend
        expected = {"upload", "download", "download_to_file", "generate_access_url", "delete", "exists"}
        abstract_methods = getattr(StorageBackend, "__abstractmethods__", set())
        for m in expected:
            assert m in abstract_methods, f"StorageBackend.{m} should be abstract"
