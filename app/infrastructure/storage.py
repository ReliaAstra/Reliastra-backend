"""S3-compatible evidence object storage abstraction."""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta

from minio import Minio


class ObjectStorage:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False
    ) -> None:
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.bucket = bucket

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload_bytes(self, key: str, content: bytes, content_type: str) -> None:
        self.ensure_bucket()
        self.client.put_object(
            self.bucket, key, io.BytesIO(content), len(content), content_type=content_type
        )

    def presign(self, key: str, ttl: timedelta = timedelta(hours=1)) -> str:
        return self.client.presigned_get_object(self.bucket, key, expires=ttl)

    async def async_presign(self, key: str, ttl: timedelta = timedelta(hours=1)) -> str:
        return await asyncio.to_thread(self.presign, key, ttl)
