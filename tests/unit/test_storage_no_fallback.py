"""Tests for FIX 35: the storage client raises instead of falling back."""

import pytest

from app.infrastructure.storage import StorageClient, StorageError


def test_upload_raises_when_backend_uninitialized():
    client = StorageClient(
        endpoint="localhost:1", access_key="x", secret_key="y", bucket="b"
    )
    # Point the client at an unreachable backend and force the uninitialized
    # state (a MinIO constructor failure leaves backend == "none").
    client._backend = "none"
    client._minio_client = None
    client._boto3_client = None

    with pytest.raises(StorageError):
        client.upload_bytes(b"data", "evidence/1.pdf")


def test_download_raises_when_backend_uninitialized():
    client = StorageClient(
        endpoint="localhost:1", access_key="x", secret_key="y", bucket="b"
    )
    client._backend = "none"
    with pytest.raises(StorageError):
        client.download_bytes("evidence/1.pdf")


def test_presigned_url_raises_when_backend_uninitialized():
    client = StorageClient(
        endpoint="localhost:1", access_key="x", secret_key="y", bucket="b"
    )
    client._backend = "none"
    with pytest.raises(StorageError):
        client.get_presigned_url("evidence/1.pdf")


def test_upload_reraises_s3_failure_as_storage_error(monkeypatch):
    client = StorageClient(
        endpoint="localhost:1", access_key="x", secret_key="y", bucket="b"
    )
    client._backend = "minio"

    class FakeBucketClient:
        def bucket_exists(self, name):
            return True

        def put_object(self, **kwargs):
            raise OSError("connection refused")

    client._minio_client = FakeBucketClient()

    with pytest.raises(StorageError):
        client.upload_bytes(b"data", "evidence/1.pdf")


def test_no_local_fallback_directory():
    """The old local fallback dir must no longer be created/used."""
    import tempfile
    import os

    client = StorageClient(
        endpoint="localhost:1", access_key="x", secret_key="y", bucket="b"
    )
    assert not hasattr(client, "_local_fallback_dir")
    fallback_dir = os.path.join(tempfile.gettempdir(), "reliastra_storage")
    assert "local" not in dir(client)
