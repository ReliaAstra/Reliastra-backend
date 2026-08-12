from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_KNOWN_INSECURE_SECRETS = {
    "reliastra-super-secret-key-that-is-at-least-32-characters-long-for-security",
    "reliastra-dev-only-change-in-production-key",
    "changeme",
    "secret",
    "your-secret-key-here",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/reliastra",
        description="Database connection URL with asyncpg driver",
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    SECRET_KEY: str = Field(
        default="reliastra-super-secret-key-that-is-at-least-32-characters-long-for-security",
        min_length=32,
        description="Secret key for JWT and encryption",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        description="Access token expiration time in minutes",
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        description="Refresh token expiration time in days",
    )
    MINIO_ENDPOINT: str = Field(
        default="localhost:9000",
        description="MinIO/S3 server endpoint",
    )
    MINIO_ACCESS_KEY: str = Field(
        default="minioadmin",
        description="MinIO/S3 access key",
    )
    MINIO_SECRET_KEY: str = Field(
        default="minioadmin",
        description="MinIO/S3 secret key",
    )
    MINIO_BUCKET: str = Field(
        default="reliastra-evidence",
        description="MinIO/S3 default storage bucket",
    )
    MINIO_USE_SSL: bool = Field(
        default=False,
        description="Whether to use SSL when connecting to MinIO/S3",
    )
    SMTP_HOST: str = Field(
        default="localhost",
        description="SMTP server host",
    )
    SMTP_PORT: int = Field(
        default=1025,
        description="SMTP server port",
    )
    SMTP_FROM: str = Field(
        default="noreply@reliastra.com",
        description="Default sender email address",
    )
    SMTP_USERNAME: str = Field(
        default="",
        description="SMTP username for authenticated relaying (optional)",
    )
    SMTP_PASSWORD: str = Field(
        default="",
        description="SMTP password for authenticated relaying (optional)",
    )
    SMTP_TLS: bool = Field(
        default=False,
        description="Enable STARTTLS (RFC 3207) on the SMTP connection (recommended for production)",
    )
    SMTP_SSL: bool = Field(
        default=False,
        description="Use implicit TLS/SSL on the SMTP connection (SMTPS on a dedicated port)",
    )
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins (must be explicit when credentials=True)",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Whether to allow cookies/credentials in CORS requests",
    )
    STRIPE_WEBHOOK_SECRET: str = Field(
        default="",
        description="Deprecated: Stripe webhook signing secret (kept for legacy compat)",
    )
    # Payment provider abstraction — default provider is Paystack (see Phase 9).
    PAYMENT_PROVIDER: str = Field(
        default="paystack",
        description="Active payment provider: 'paystack', 'stripe', or 'manual'",
    )
    PAYSTACK_SECRET_KEY: str = Field(
        default="",
        description="Paystack secret key for server-side API calls",
    )
    PAYSTACK_PUBLIC_KEY: str = Field(
        default="",
        description="Paystack public key for client-side Paystack.js integration",
    )
    PAYSTACK_WEBHOOK_SECRET: str = Field(
        default="",
        description="Paystack webhook signing secret for event verification",
    )
    PAYSTACK_CALLBACK_URL: str = Field(
        default="http://localhost:3000/billing/callback",
        description="URL Paystack redirects the customer to after payment",
    )
    # SSRF protection tuning. Loopback is allowed by default for local
    # development and integration tests, but must be disabled in production
    # to prevent internal-service probing.
    SSRF_ALLOW_LOOPBACK: bool = Field(
        default=True,
        description="Allow requests to loopback (127.0.0.1) addresses",
    )
    SSRF_ALLOWED_CIDRS: list[str] = Field(
        default=[],
        description="Extra CIDR ranges allowed through SSRF protection (development only)",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Current environment (development, staging, production)",
    )

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> type[Settings]:
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY in _KNOWN_INSECURE_SECRETS:
                raise ValueError(
                    "SECRET_KEY must be changed from the default value in production. "
                    "Set a cryptographically random SECRET_KEY environment variable."
                )
            if self.MINIO_SECRET_KEY == "minioadmin":
                logger.warning("MINIO_SECRET_KEY is set to the default 'minioadmin' in production")
            if self.SSRF_ALLOW_LOOPBACK:
                logger.warning(
                    "SSRF_ALLOW_LOOPBACK is enabled in production; "
                    "loopback should be blocked in production environments"
                )
        return self

    @property
    def fernet_key(self) -> bytes:
        """Derive a 32-byte url-safe base64-encoded key from SECRET_KEY for Fernet encryption."""
        key_hash = hashlib.sha256(self.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(key_hash)


settings = Settings()
