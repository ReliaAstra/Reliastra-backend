import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Raised when object storage is unavailable or an operation fails.

    FIX 35: there is deliberately NO local-filesystem fallback. Silently
    writing evidence artifacts to ``/tmp`` (and returning success) loses data
    that SLA reports depend on. Callers (Celery tasks) let the exception
    propagate so the task retries until the object store is healthy again.
    """


class StorageClient:
    """Supabase Storage S3 client (boto3 — the only supported backend).

    One provider, one code path: every operation goes through a boto3 S3
    client configured for the Supabase S3-compatible API with path-style
    addressing and the ``s3v4`` signature version.

    The boto3 client is built lazily on first use so that importing
    ``app.main`` never fails when storage is unconfigured (e.g. local dev or
    CI without Supabase S3 credentials).  The first storage operation then
    raises ``StorageError`` instead.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        self.endpoint = (
            endpoint if endpoint is not None else settings.SUPABASE_S3_ENDPOINT
        ).rstrip("/")
        self.access_key = (
            access_key if access_key is not None else settings.SUPABASE_S3_ACCESS_KEY_ID
        )
        self.secret_key = (
            secret_key
            if secret_key is not None
            else settings.SUPABASE_S3_SECRET_ACCESS_KEY
        )
        self.bucket = bucket if bucket is not None else settings.SUPABASE_S3_BUCKET
        self.region = region if region is not None else settings.SUPABASE_S3_REGION
        self._client: Any = None

    # ------------------------------------------------------------------
    # Client initialisation (lazy — never at import time)
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Build (once) and return the boto3 S3 client.

        Raises ``StorageError`` when the Supabase S3 configuration is
        incomplete or the client cannot be constructed.
        """
        if self._client is None:
            missing = [
                name
                for name, value in (
                    ("SUPABASE_S3_ENDPOINT", self.endpoint),
                    ("SUPABASE_S3_REGION", self.region),
                    ("SUPABASE_S3_ACCESS_KEY_ID", self.access_key),
                    ("SUPABASE_S3_SECRET_ACCESS_KEY", self.secret_key),
                    ("SUPABASE_S3_BUCKET", self.bucket),
                )
                if not value
            ]
            if missing:
                raise StorageError(
                    "Supabase Storage S3 is not configured — missing: "
                    + ", ".join(missing)
                    + ". Set them from the Supabase dashboard "
                    "(Storage → S3 Access Keys)."
                )
            try:
                import boto3
                from botocore.config import Config as BotoConfig

                self._client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                    config=BotoConfig(
                        signature_version="s3v4",
                        s3={"addressing_style": "path"},
                    ),
                )
                logger.info(
                    "Supabase Storage S3 client initialized (endpoint=%s, region=%s)",
                    self.endpoint,
                    self.region,
                )
            except StorageError:
                raise
            except Exception as exc:
                raise StorageError(
                    f"Could not initialize Supabase Storage S3 client: {exc}"
                ) from exc
        return self._client

    # ------------------------------------------------------------------
    # Bucket helpers
    # ------------------------------------------------------------------

    def ensure_bucket_exists(self) -> None:
        """Verify the configured bucket exists on Supabase Storage.

        Buckets are provisioned in the Supabase dashboard — the app never
        auto-creates them.  Raises ``StorageError`` (naming the bucket) when
        the bucket is missing or the store is unreachable (FIX 35).
        """
        client = self._get_client()
        try:
            client.head_bucket(Bucket=self.bucket)
        except Exception as exc:
            raise StorageError(
                f"Supabase Storage bucket '{self.bucket}' is missing or "
                f"unreachable: {exc}. Create the bucket in the Supabase "
                "dashboard (Storage → New bucket) and set SUPABASE_S3_BUCKET "
                "to its name."
            ) from exc

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
        client = self._get_client()
        try:
            client.put_object(
                Bucket=self.bucket,
                Key=object_name,
                Body=data,
                ContentType=content_type,
            )
            logger.info(
                "Uploaded object '%s' to Supabase Storage bucket '%s'",
                object_name,
                self.bucket,
            )
            return object_name
        except Exception as exc:
            raise StorageError(f"Upload of '{object_name}' failed: {exc}") from exc

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
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self.bucket, Key=object_name)
            return response["Body"].read()
        except Exception as exc:
            raise StorageError(f"Download of '{object_name}' failed: {exc}") from exc

    def download_file(self, object_name: str, dest_path: str) -> None:
        data = self.download_bytes(object_name)
        with open(dest_path, "wb") as f:
            f.write(data)

    # ------------------------------------------------------------------
    # Presigned URL
    # ------------------------------------------------------------------

    def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        # FIX 35: raise on any storage failure — no fake local preview URLs.
        self.ensure_bucket_exists()
        client = self._get_client()
        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_name},
                ExpiresIn=expires_seconds,
            )
            return str(url)
        except Exception as exc:
            raise StorageError(
                f"Presigned URL generation for '{object_name}' failed: {exc}"
            ) from exc


storage_client = StorageClient()
