import io
import os
import types

import pytest


def test_fetch_tenant_object_to_tempfile_validates_tenant_bucket_and_size(monkeypatch, tmp_path):
    import src.core.gcs_client as mod

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")
    monkeypatch.setenv("GCS_BUCKET_PREFIX", "tnt")

    captured = {"opened": False, "reload": False}

    class _BlobFile(io.BytesIO):
        def __enter__(self):
            captured["opened"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Blob:
        def __init__(self, *, data: bytes, content_type: str, size: int):
            self._data = data
            self.content_type = content_type
            self.size = size

        def reload(self):
            captured["reload"] = True

        def open(self, mode):
            assert mode == "rb"
            return _BlobFile(self._data)

    class _Bucket:
        def __init__(self, blob):
            self._blob = blob

        def blob(self, _name):
            return self._blob

    class _Client:
        def __init__(self, project=None):
            self.project = project

        def bucket(self, _name):
            return _Bucket(_Blob(data=b"hello", content_type="text/plain", size=5))

    monkeypatch.setattr(mod.storage, "Client", _Client)

    fd, local_path = None, None

    def _mkstemp(prefix, dir):
        nonlocal fd, local_path
        p = tmp_path / f"{prefix}out"
        local_path = str(p)
        fd = os.open(local_path, os.O_CREAT | os.O_WRONLY)
        return fd, local_path

    monkeypatch.setattr(mod.tempfile, "mkstemp", _mkstemp)

    obj = mod.fetch_tenant_object_to_tempfile(
        tenant_id="110",
        gcs_uri="gs://tnt-110-media/uploads/abc/file.txt",
        max_size_bytes=10,
    )

    assert captured["reload"] is True
    assert captured["opened"] is True
    assert obj.tenant_id == "110"
    assert obj.bucket_name == "tnt-110-media"
    assert obj.object_name.endswith("file.txt")
    assert obj.content_type == "text/plain"
    assert obj.size_bytes == 5
    assert os.path.exists(obj.local_path)
    with open(obj.local_path, "rb") as f:
        assert f.read() == b"hello"

    os.unlink(obj.local_path)

    with pytest.raises(ValueError):
        mod.fetch_tenant_object_to_tempfile(
            tenant_id="110",
            gcs_uri="gs://tnt-999-media/uploads/abc/file.txt",
            max_size_bytes=10,
        )

    with pytest.raises(ValueError):
        mod.fetch_tenant_object_to_tempfile(
            tenant_id="110",
            gcs_uri="gs://tnt-110-media/uploads/abc/file.txt",
            max_size_bytes=2,
        )


def test_fetch_tenant_object_to_tempfile_infers_content_type(monkeypatch, tmp_path):
    import src.core.gcs_client as mod

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "dummy-project")
    monkeypatch.setenv("GCS_BUCKET_PREFIX", "tnt")

    class _BlobFile(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Blob:
        def __init__(self, *, data: bytes):
            self._data = data
            self.content_type = ""
            self.size = len(data)

        def reload(self):
            return None

        def open(self, mode):
            return _BlobFile(self._data)

    class _Bucket:
        def __init__(self, blob):
            self._blob = blob

        def blob(self, _name):
            return self._blob

    class _Client:
        def __init__(self, project=None):
            self.project = project

        def bucket(self, _name):
            return _Bucket(_Blob(data=b"%PDF"))

    monkeypatch.setattr(mod.storage, "Client", _Client)

    def _mkstemp(prefix, dir):
        p = tmp_path / f"{prefix}out"
        fd = os.open(str(p), os.O_CREAT | os.O_WRONLY)
        return fd, str(p)

    monkeypatch.setattr(mod.tempfile, "mkstemp", _mkstemp)

    obj = mod.fetch_tenant_object_to_tempfile(
        tenant_id="110",
        gcs_uri="gs://tnt-110-media/uploads/abc/doc.pdf",
        max_size_bytes=10,
    )

    assert obj.content_type == "application/pdf"
    os.unlink(obj.local_path)
