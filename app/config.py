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
    TRUSTED_PROXY_HOPS: int = Field(
        default=1,
        description="Number of trusted reverse-proxy hops used when parsing "
                    "X-Forwarded-For for rate limiting",
    )
    # ── Supabase Authentication ──────────────────────────────────────────
    SUPABASE_URL: str = Field(
        default="",
        description="Supabase project URL (e.g. https://xyz.supabase.co). "
                    "When set, the API accepts Supabase JWTs in addition to "
                    "native Reliastra tokens.",
    )
    SUPABASE_JWT_SECRET: str = Field(
        default="",
        description="Supabase JWT secret (the `SUPABASE_JWT_SECRET` from "
                    "project settings -> API -> JWT Settings). Used to verify "
                    "RS256 JWTs issued by Supabase Auth.",
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

    # Admin panel bootstrap
    FIRST_ADMIN_EMAIL: str | None = Field(
        default=None,
        description="Email of the first system admin to auto-promote on startup",
    )

    # ── Partner Network / Distribution Infrastructure ────────────────────────
    # Canonical public origin used to build partner referral links. NEVER
    # hardcode "https://reliastra.com" anywhere in the codebase — read it here.
    RELIASTRA_PUBLIC_URL: str = Field(
        default="https://reliastra.com",
        description="Canonical public website origin used to build partner "
                    "referral links (https://<origin>/r/{partner_code}).",
    )
    PARTNER_REFERRAL_PATH_PREFIX: str = Field(
        default="/r",
        description="Path prefix for canonical partner referral links.",
    )
    PARTNER_ATTRIBUTION_WINDOW_DAYS: int = Field(
        default=90,
        ge=1,
        le=730,
        description="Last-touch attribution window in days. A click older "
                    "than this no longer attributes a signup to the partner.",
    )
    PARTNER_COMMISSION_HOLD_DAYS: int = Field(
        default=30,
        ge=0,
        le=365,
        description="Holding period (days) between a commission being earned "
                    "and becoming payable, covering refunds and chargebacks.",
    )
    PARTNER_DEFAULT_CURRENCY: str = Field(
        default="USD",
        description="Default ISO-4217 currency for partner money amounts. "
                    "All amounts are stored as integer minor units.",
    )
    # Economics — expressed in basis points (1 bps = 0.01%) so that all money
    # math stays in integers. 2000 bps = 20%.
    PARTNER_RATE_REFER_BPS: int = Field(
        default=2000,
        ge=0,
        le=10000,
        description="Recurring commission rate (bps) for REFER relationships.",
    )
    PARTNER_RATE_DEPLOY_BPS: int = Field(
        default=3000,
        ge=0,
        le=10000,
        description="Recurring commission rate (bps) for DEPLOY relationships.",
    )
    PARTNER_RATE_CREATE_BPS: int = Field(
        default=2500,
        ge=0,
        le=10000,
        description="Recurring commission rate (bps) for CREATE relationships.",
    )
    PARTNER_RATE_INTRODUCE_BPS: int = Field(
        default=1500,
        ge=0,
        le=10000,
        description="Year-1 commission rate (bps) for INTRODUCE relationships.",
    )
    PARTNER_RATE_RESELL_BPS: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="Commission rate (bps) for RESELL relationships. Resellers "
                    "earn the wholesale margin, never a platform commission.",
    )
    PARTNER_MAX_TOTAL_COMMISSION_BPS: int = Field(
        default=5000,
        ge=0,
        le=10000,
        description="Hard ceiling on the combined commission rate applied to a "
                    "single collected payment (bps of ACTUAL collected revenue).",
    )
    PARTNER_INTRODUCE_WINDOW_MONTHS: int = Field(
        default=12,
        ge=1,
        le=60,
        description="Year-1 window (months) during which INTRODUCE commissions "
                    "accrue on collected revenue.",
    )
    PARTNER_MIN_PAYOUT_MINOR: int = Field(
        default=5000,
        ge=0,
        description="Minimum payable balance (integer minor units) required "
                    "before a partner can request a payout.",
    )
    PARTNER_CLICK_DEDUP_WINDOW_SECONDS: int = Field(
        default=1800,
        ge=0,
        description="Window in which repeated clicks from the same visitor "
                    "fingerprint on the same link are deduplicated.",
    )
    PARTNER_FRAUD_REVIEW_SCORE: int = Field(
        default=70,
        ge=0,
        le=100,
        description="Risk score at or above which a partner's commissions are "
                    "held for manual review instead of becoming payable.",
    )
    PARTNER_AUTO_APPROVE_APPLICATIONS: bool = Field(
        default=False,
        description="Auto-approve partner applications (non-production only).",
    )
    MAXMIND_LICENSE_KEY: str = Field(
        default="",
        description="MaxMind license key used to download/refresh the local "
                    "GeoLite2-Country database. Never used per-request.",
    )
    MAXMIND_ACCOUNT_ID: str = Field(
        default="",
        description="MaxMind account id paired with MAXMIND_LICENSE_KEY.",
    )
    MAXMIND_DB_PATH: str = Field(
        default="/var/lib/geoip/GeoLite2-City.mmdb",
        description="Filesystem path to the local MaxMind GeoLite2 database. "
                    "Lookups are local + cached; no external call per request.",
    )
    MAXMIND_CACHE_TTL_SECONDS: int = Field(
        default=86400,
        ge=0,
        description="Redis TTL for cached IP→geo lookups.",
    )

    @property
    def partner_referral_base_url(self) -> str:
        """Canonical base for partner referral links, without trailing slash."""
        origin = self.RELIASTRA_PUBLIC_URL.rstrip("/")
        prefix = "/" + self.PARTNER_REFERRAL_PATH_PREFIX.strip("/")
        return f"{origin}{prefix}"

    @property
    def fernet_key(self) -> bytes:
        """Derive a 32-byte url-safe base64-encoded key from SECRET_KEY for Fernet encryption."""
        key_hash = hashlib.sha256(self.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(key_hash)


settings = Settings()
