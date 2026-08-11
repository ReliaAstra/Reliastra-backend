"""Shared test configuration and factories."""

from __future__ import annotations

from app.config import Settings


def settings_factory() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost:5432/reliastra_test",
        redis_url="redis://localhost:6379/15",
        secret_key="test-secret-key-that-is-longer-than-32-characters",
        minio_endpoint="localhost:9000",
        minio_access_key="test-access",
        minio_secret_key="test-secret",
        minio_bucket="test-evidence",
    )
