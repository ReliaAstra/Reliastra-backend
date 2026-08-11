"""Validated runtime configuration; values come exclusively from the environment."""

from __future__ import annotations

from functools import cached_property

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Reliastra API"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    database_replica_url: str | None = None
    redis_url: str
    secret_key: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)

    minio_endpoint: str
    minio_access_key: SecretStr
    minio_secret_key: SecretStr
    minio_bucket: str = "reliastra-evidence"
    minio_use_ssl: bool = False

    smtp_host: str = "mailhog"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from: str = "noreply@reliastra.com"
    cors_origins: str = ""

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]
