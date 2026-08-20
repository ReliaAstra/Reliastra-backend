"""Tests for FIX 35: the storage client raises instead of falling back.

The storage layer is Supabase Storage (S3) via boto3 only — there is no
second backend, no auto-detection, and no local-filesystem fallback.  These
tests assert that every failure mode raises ``StorageError`` so Celery tasks
retry instead of silently succeeding.
"""

import pytest

from app.config import Settings
from app.infrastructure.storage import StorageClient, StorageError

VALID_ENDPOINT = "https://abcxyz.supabase.co/storage/v1/s3"


def _unconfigured_client() -> StorageClient:
    """A client with explicitly empty config — no Supabase S3 credentials."""
    return StorageClient(
        endpoint="", access_key="", secret_key="", bucket="", region=""
    )


def _configured_client() -> StorageClient:
    return StorageClient(
        endpoint=VALID_ENDPOINT,
        access_key="test-access-key",
        secret_key="test-secret-key",
        bucket="test-bucket",
        region="eu-west-3",
    )


# ---------------------------------------------------------------------------
# Uninitialized / unconfigured client raises StorageError on first use
# ---------------------------------------------------------------------------


def test_upload_raises_when_client_unconfigured():
    client = _unconfigured_client()
    with pytest.raises(StorageError):
        client.upload_bytes(b"data", "evidence/1.pdf")


def test_download_raises_when_client_unconfigured():
    client = _unconfigured_client()
    with pytest.raises(StorageError):
        client.download_bytes("evidence/1.pdf")


def test_presigned_url_raises_when_client_unconfigured():
    client = _unconfigured_client()
    with pytest.raises(StorageError):
        client.get_presigned_url("evidence/1.pdf")


# ---------------------------------------------------------------------------
# S3 operation failures are re-raised as StorageError (no fallback)
# ---------------------------------------------------------------------------


class _FakeS3Client:
    """Minimal boto3-shaped fake — no network involved."""

    def head_bucket(self, Bucket):
        return None

    def put_object(self, **kwargs):
        raise OSError("connection refused")

    def get_object(self, **kwargs):
        raise OSError("connection refused")

    def generate_presigned_url(self, *args, **kwargs):
        raise OSError("connection refused")


def test_upload_reraises_s3_failure_as_storage_error(monkeypatch):
    client = _configured_client()
    monkeypatch.setattr(client, "_get_client", lambda: _FakeS3Client())

    with pytest.raises(StorageError):
        client.upload_bytes(b"data", "evidence/1.pdf")


def test_download_reraises_s3_failure_as_storage_error(monkeypatch):
    client = _configured_client()
    monkeypatch.setattr(client, "_get_client", lambda: _FakeS3Client())

    with pytest.raises(StorageError):
        client.download_bytes("evidence/1.pdf")


def test_presign_reraises_s3_failure_as_storage_error(monkeypatch):
    client = _configured_client()
    monkeypatch.setattr(client, "_get_client", lambda: _FakeS3Client())

    with pytest.raises(StorageError):
        client.get_presigned_url("evidence/1.pdf")


# ---------------------------------------------------------------------------
# Bucket verification: verify-only, never auto-create
# ---------------------------------------------------------------------------


def test_missing_bucket_raises_storage_error_naming_the_bucket(monkeypatch):
    from botocore.exceptions import ClientError

    class MissingBucketClient:
        def head_bucket(self, Bucket):
            raise ClientError(
                {
                    "Error": {
                        "Code": "404",
                        "Message": "Not Found",
                    }
                },
                "HeadBucket",
            )

    client = StorageClient(
        endpoint=VALID_ENDPOINT,
        access_key="test-access-key",
        secret_key="test-secret-key",
        bucket="dev-evidence-bucket",
        region="eu-west-3",
    )
    monkeypatch.setattr(client, "_get_client", lambda: MissingBucketClient())

    with pytest.raises(StorageError, match="dev-evidence-bucket"):
        client.ensure_bucket_exists()


def test_no_local_fallback_directory():
    """The old local fallback dir must no longer be created/used."""
    import os
    import tempfile

    client = _configured_client()
    assert not hasattr(client, "_local_fallback_dir")
    fallback_dir = os.path.join(tempfile.gettempdir(), "reliastra_storage")
    assert "local" not in dir(client)
    assert not os.path.exists(fallback_dir)


# ---------------------------------------------------------------------------
# boto3 client configuration: path-style addressing + s3v4, real region
# ---------------------------------------------------------------------------


def test_boto3_client_uses_path_style_addressing_and_s3v4():
    client = _configured_client()

    boto3_client = client._get_client()
    meta = boto3_client.meta

    # Supabase Storage requires path-style addressing and s3v4 signatures.
    assert meta.config.s3["addressing_style"] == "path"
    assert meta.config.signature_version == "s3v4"
    # The full endpoint URL is passed through verbatim, and the region is
    # the caller-provided project region (never silently defaulted).
    assert meta.endpoint_url == VALID_ENDPOINT
    assert meta.region_name == "eu-west-3"


# ---------------------------------------------------------------------------
# Config validation: Supabase S3 endpoint only, https only
# ---------------------------------------------------------------------------


def test_config_rejects_non_https_endpoint():
    with pytest.raises(ValueError, match="https"):
        Settings(
            _env_file=None,
            SUPABASE_S3_ENDPOINT="http://abcxyz.supabase.co/storage/v1/s3",
        )


def test_config_rejects_non_supabase_s3_endpoint():
    with pytest.raises(ValueError, match="storage/v1/s3"):
        Settings(
            _env_file=None,
            SUPABASE_S3_ENDPOINT="https://s3.amazonaws.com",
        )


def test_config_accepts_supabase_endpoint_and_strips_trailing_slash():
    parsed = Settings(
        _env_file=None,
        SUPABASE_S3_ENDPOINT="https://abcxyz.supabase.co/storage/v1/s3/",
    )
    assert parsed.SUPABASE_S3_ENDPOINT == VALID_ENDPOINT


def test_production_requires_complete_supabase_s3_config(monkeypatch):
    for var in (
        "SUPABASE_S3_ENDPOINT",
        "SUPABASE_S3_REGION",
        "SUPABASE_S3_ACCESS_KEY_ID",
        "SUPABASE_S3_SECRET_ACCESS_KEY",
        "SUPABASE_S3_BUCKET",
    ):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValueError, match="SUPABASE_S3"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="x" * 48,
        )
