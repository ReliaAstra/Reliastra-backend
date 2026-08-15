from __future__ import annotations

import base64
import hashlib
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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
        description="Database connection URL with asyncpg driver. "
                    "Accepts both internal and external PostgreSQL URLs (e.g. Supabase, Neon, RDS). "
                    "For SSL databases, set DATABASE_SSL_MODE=require.",
    )
    DATABASE_SSL_MODE: str = Field(
        default="",
        description="PostgreSQL SSL mode (e.g. 'require', 'verify-full'). "
                    "Appended to DATABASE_URL if set. "
                    "Supabase and most managed Postgres services require 'require'.",
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
    MINIO_REGION: str = Field(
        default="",
        description="S3 region (e.g. 'eu-west-3' for Supabase, 'us-east-1' for AWS). Leave empty for local MinIO.",
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
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins (must be explicit when credentials=True)",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Whether to allow cookies/credentials in CORS requests",
    )
    PAYSTACK_SECRET_KEY: str = Field(
        default="",
        description="Paystack secret key used for API calls and webhook signing",
    )
    PAYSTACK_PUBLIC_KEY: str = Field(
        default="",
        description="Paystack public key for payment initialization",
    )
    PAYSTACK_BASE_URL: str = Field(
        default="https://api.paystack.co",
        description="Paystack API base URL",
    )
    SMTP_USE_TLS: bool = Field(
        default=False,
        description="Whether to negotiate SMTP TLS when supported",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Current environment (development, staging, production)",
    )

    @property
    def database_url_with_ssl(self) -> str:
        """Return DATABASE_URL with SSL parameters applied if configured.

        Only PostgreSQL URLs get sslmode appended; SQLite and other drivers
        are returned unchanged.  Also normalises bare ``postgresql://`` URLs
        to ``postgresql+asyncpg://`` so that ``create_async_engine`` picks
        the correct driver even when the environment variable omits it.
        """
        url = self.DATABASE_URL
        # Normalise bare postgresql:// → postgresql+asyncpg://
        if url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not self.DATABASE_SSL_MODE or not url.startswith("postgresql"):
            return url
        parsed = urlparse(url)
        existing_params = parse_qs(parsed.query, keep_blank_values=True)
        existing_params["sslmode"] = [self.DATABASE_SSL_MODE]
        new_query = urlencode(existing_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    @property
    def minio_region_or_none(self) -> str | None:
        """Return MINIO_REGION as None when empty so the Minio client auto-detects."""
        return self.MINIO_REGION if self.MINIO_REGION else None

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
        return self

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str | None = Field(
        default=None,
        description="Google OAuth 2.0 client ID",
    )
    GOOGLE_CLIENT_SECRET: str | None = Field(
        default=None,
        description="Google OAuth 2.0 client secret",
    )
    GOOGLE_REDIRECT_URI: str | None = Field(
        default=None,
        description="Google OAuth redirect URI (e.g. https://yourapp.com/auth/google/callback)",
    )
    GOOGLE_AUTH_ENABLED: bool = Field(
        default=False,
        description="Enable/disable Google OAuth authentication",
    )

    # GitHub OAuth settings
    GITHUB_CLIENT_ID: str | None = Field(
        default=None,
        description="GitHub OAuth client ID",
    )
    GITHUB_CLIENT_SECRET: str | None = Field(
        default=None,
        description="GitHub OAuth client secret",
    )
    GITHUB_REDIRECT_URI: str | None = Field(
        default=None,
        description="GitHub OAuth redirect URI (e.g. https://yourapp.com/auth/github/callback)",
    )
    GITHUB_AUTH_ENABLED: bool = Field(
        default=False,
        description="Enable/disable GitHub OAuth authentication",
    )

    # Email verification & password reset
    FRONTEND_BASE_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend base URL for email verification and password reset links",
    )
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = Field(
        default=60,
        description="Email verification token lifetime in minutes",
    )
    PASSWORD_RESET_EXPIRE_MINUTES: int = Field(
        default=15,
        description="Password reset token lifetime in minutes",
    )

    @property
    def fernet_key(self) -> bytes:
        """Derive a 32-byte url-safe base64-encoded key from SECRET_KEY for Fernet encryption."""
        key_hash = hashlib.sha256(self.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(key_hash)


settings = Settings()
