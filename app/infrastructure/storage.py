import io
import logging
from typing import Any
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Raised when object storage is unavailable or an operation fails.

    FIX 35: there is deliberately NO local-filesystem fallback. Silently
    writing evidence artifacts to ``/tmp`` (and returning success) loses data
    that SLA reports depend on. Callers (Celery tasks) let the exception
    propagate so the task retries until the object store is healthy again.
    """

# ---------------------------------------------------------------------------
# Determine whether the configured endpoint needs boto3 (path-style / S3
# providers like Supabase, AWS, R2) or the lightweight minio SDK (local
# MinIO without a path prefix).  The minio SDK rejects paths in endpoints,
# so any endpoint containing a "/" after the host is routed to boto3.
# ---------------------------------------------------------------------------


def _endpoint_has_path(endpoint: str) -> bool:
    """Return True if the endpoint string contains a path component."""
    parsed = urlparse(f"//{endpoint}")
    return bool(parsed.path and parsed.path != "/")


class StorageClient:
    """S3-compatible storage client.

    Automatically selects the best backend:
    * **boto3** — when the endpoint contains a path (e.g. Supabase S3) or when
      a region is explicitly set.  boto3 supports arbitrary ``endpoint_url``
      values including those with path prefixes.
    * **minio** — lightweight SDK used for simple ``host:port`` endpoints
      (typically local MinIO).

    Both backends expose the same public API: ``upload_bytes``,
    ``download_bytes``, ``get_presigned_url``, etc.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        use_ssl: bool | None = None,
        region: str | None = None,
    ) -> None:
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket = bucket or settings.MINIO_BUCKET
        self.use_ssl = (
            use_ssl if use_ssl is not None else settings.MINIO_USE_SSL
        )
        self.region = region or settings.minio_region_or_none
        self._backend: str = "none"  # "boto3" | "minio" | "none"
        self._boto3_client: Any = None
        self._minio_client: Any = None
        self._init_client()

    # ------------------------------------------------------------------
    # Client initialisation
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        use_boto3 = _endpoint_has_path(self.endpoint) or bool(self.region)
        if use_boto3:
            self._init_boto3()
        else:
            self._init_minio()

    def _init_boto3(self) -> None:
        try:
            import boto3
            from botocore.config import Config as BotoConfig

            scheme = "https" if self.use_ssl else "http"
            endpoint_url = f"{scheme}://{self.endpoint}"

            self._boto3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region or "us-east-1",
                config=BotoConfig(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                ),
            )
            self._backend = "boto3"
            logger.info(
                "Storage backend: boto3 (endpoint=%s, region=%s)",
                self.endpoint,
                self.region,
            )
        except Exception as exc:
            logger.warning("Could not initialize boto3 S3 client: %s", exc)
            self._backend = "none"

    def _init_minio(self) -> None:
        try:
            from minio import Minio

            self._minio_client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.use_ssl,
            )
            self._backend = "minio"
            logger.info("Storage backend: minio (endpoint=%s)", self.endpoint)
        except Exception as exc:
            logger.warning("Could not initialize Minio client: %s", exc)
            self._backend = "none"

    @property
    def client(self):
        """Return whichever underlying client is active (for compatibility)."""
        return self._boto3_client or self._minio_client

    # ------------------------------------------------------------------
    # Bucket helpers
    # ------------------------------------------------------------------

    def ensure_bucket_exists(self) -> None:
        """Verify (and create, if missing) the target bucket. Raises
        ``StorageError`` when the object store is unusable (FIX 35)."""
        if self._backend == "none":
            raise StorageError(
                "Object storage client is not initialized — "
                "check MINIO_ENDPOINT / MINIO credentials"
            )
        try:
            if self._backend == "boto3":
                self._boto3_client.head_bucket(Bucket=self.bucket)
            else:
                if not self._minio_client.bucket_exists(self.bucket):
                    self._minio_client.make_bucket(self.bucket)
        except Exception as exc:
            # Bucket missing (404) — attempt to create it. Only the boto3
            # backend exposes ``exceptions.ClientError``; guarding on the
            # backend prevents an AttributeError when boto3 is unavailable.
            if self._backend == "boto3" and self._boto3_client is not None:
                client_error = getattr(
                    self._boto3_client.exceptions, "ClientError", ()
                )
                if isinstance(exc, client_error):
                    try:
                        self._boto3_client.create_bucket(Bucket=self.bucket)
                        return
                    except Exception as create_exc:
                        raise StorageError(
                            f"S3 bucket creation failed: {create_exc}"
                        ) from create_exc
            raise StorageError(f"S3 bucket check failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/pdf",
    ) -> str:
        # FIX 35: raise on any storage failure — no silent local fallback.
        self.ensure_bucket_exists()
        try:
            if self._backend == "boto3":
                self._boto3_client.put_object(
                    Bucket=self.bucket,
                    Key=object_name,
                    Body=data,
                    ContentType=content_type,
                )
            else:
                self._minio_client.put_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    data=io.BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
            logger.info(
                "Uploaded object '%s' to bucket '%s' via %s",
                object_name,
                self.bucket,
                self._backend,
            )
            return object_name
        except Exception as exc:
            raise StorageError(
                f"Upload of '{object_name}' failed: {exc}"
            ) from exc

    def upload_file(
        self,
        file_path: str,
        object_name: str,
        content_type: str = "application/pdf",
    ) -> str:
        with open(file_path, "rb") as f:
            data = f.read()
        return self.upload_bytes(data, object_name, content_type)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_bytes(self, object_name: str) -> bytes:
        # FIX 35: raise on any storage failure — no silent local fallback.
        self.ensure_bucket_exists()
        try:
            if self._backend == "boto3":
                response = self._boto3_client.get_object(
                    Bucket=self.bucket, Key=object_name
                )
                data = response["Body"].read()
            else:
                response = self._minio_client.get_object(self.bucket, object_name)
                data = response.read()
                response.close()
                response.release_conn()
            return data
        except Exception as exc:
            raise StorageError(
                f"Download of '{object_name}' failed: {exc}"
            ) from exc

    def download_file(self, object_name: str, dest_path: str) -> None:
        data = self.download_bytes(object_name)
        with open(dest_path, "wb") as f:
            f.write(data)

    # ------------------------------------------------------------------
    # Presigned URL
    # ------------------------------------------------------------------

    def get_presigned_url(
        self, object_name: str, expires_seconds: int = 3600
    ) -> str:
        # FIX 35: raise on any storage failure — no fake local preview URLs.
        self.ensure_bucket_exists()
        try:
            if self._backend == "boto3":
                url = self._boto3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": object_name},
                    ExpiresIn=expires_seconds,
                )
            else:
                from datetime import timedelta

                url = self._minio_client.presigned_get_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(seconds=expires_seconds),
                )
            return str(url)
        except Exception as exc:
            raise StorageError(
                f"Presigned URL generation for '{object_name}' failed: {exc}"
            ) from exc


storage_client = StorageClient()
