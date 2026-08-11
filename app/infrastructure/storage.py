import io
import os
import logging
import tempfile
from typing import Any
from minio import Minio
from app.config import settings

logger = logging.getLogger(__name__)


class StorageClient:
    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        use_ssl: bool | None = None,
    ) -> None:
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket = bucket or settings.MINIO_BUCKET
        self.use_ssl = (
            use_ssl if use_ssl is not None else settings.MINIO_USE_SSL
        )
        self.client: Minio | None = None
        self._local_fallback_dir: str = os.path.join(
            tempfile.gettempdir(), "reliastra_storage"
        )
        os.makedirs(self._local_fallback_dir, exist_ok=True)
        self._init_client()

    def _init_client(self) -> None:
        try:
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.use_ssl,
            )
        except Exception as exc:
            logger.warning("Could not initialize Minio client: %s", exc)
            self.client = None

    def ensure_bucket_exists(self) -> bool:
        if not self.client:
            return True
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            return True
        except Exception as exc:
            logger.warning("Minio bucket check/create failed, using local fallback: %s", exc)
            return False

    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/pdf",
    ) -> str:
        if self.ensure_bucket_exists() and self.client:
            try:
                self.client.put_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                    data=io.BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                logger.info("Uploaded object '%s' to MinIO bucket '%s'", object_name, self.bucket)
                return object_name
            except Exception as exc:
                logger.warning("MinIO upload failed, falling back to local: %s", exc)

        # Local filesystem fallback
        local_path = os.path.join(self._local_fallback_dir, object_name.replace("/", "_"))
        with open(local_path, "wb") as f:
            f.write(data)
        logger.info("Uploaded object '%s' to local fallback '%s'", object_name, local_path)
        return object_name

    def upload_file(
        self,
        file_path: str,
        object_name: str,
        content_type: str = "application/pdf",
    ) -> str:
        with open(file_path, "rb") as f:
            data = f.read()
        return self.upload_bytes(data, object_name, content_type)

    def download_bytes(self, object_name: str) -> bytes:
        if self.ensure_bucket_exists() and self.client:
            try:
                response = self.client.get_object(self.bucket, object_name)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except Exception as exc:
                logger.warning("MinIO download failed, trying local fallback: %s", exc)

        local_path = os.path.join(self._local_fallback_dir, object_name.replace("/", "_"))
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                return f.read()
        raise FileNotFoundError(f"Object {object_name} not found in storage.")

    def download_file(self, object_name: str, dest_path: str) -> None:
        data = self.download_bytes(object_name)
        with open(dest_path, "wb") as f:
            f.write(data)

    def get_presigned_url(
        self, object_name: str, expires_seconds: int = 3600
    ) -> str:
        if self.ensure_bucket_exists() and self.client:
            try:
                from datetime import timedelta
                url = self.client.presigned_get_object(
                    self.bucket,
                    object_name,
                    expires=timedelta(seconds=expires_seconds),
                )
                return str(url)
            except Exception as exc:
                logger.warning("MinIO presigned URL failed: %s", exc)

        # Return mock / local preview URL for fallback/testing
        return f"http://localhost:8000/v1/storage/download/{object_name}"


storage_client = StorageClient()
