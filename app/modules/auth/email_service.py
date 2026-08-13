import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    AppException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import get_password_hash
from app.infrastructure.email import email_client
from app.modules.auth.repository import AuthRepository
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)

# Token lifetimes
EMAIL_VERIFICATION_EXPIRE_MINUTES = 60
PASSWORD_RESET_EXPIRE_MINUTES = 15


class EmailAuthService:
    """Handles email verification and password reset flows."""

    def __init__(
        self,
        user_repository: UserRepository = UserRepository(),
        auth_repository: AuthRepository = AuthRepository(),
    ) -> None:
        self.user_repository = user_repository
        self.auth_repository = auth_repository

    def _build_verification_url(self, token: str) -> str:
        """Build the frontend verification URL."""
        base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
        return f"{base_url}/verify-email?token={token}"

    def _build_reset_url(self, token: str) -> str:
        """Build the frontend password reset URL."""
        base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
        return f"{base_url}/reset-password?token={token}"

    def _render_verification_email(self, user_name: str, verification_url: str) -> tuple[str, str]:
        """Returns (plain_text, html_body) for verification email."""
        plain = f"""
Hello {user_name},

Thank you for signing up with Reliastra. Please verify your email address by clicking the link below:

{verification_url}

This link expires in {EMAIL_VERIFICATION_EXPIRE_MINUTES} minutes.

If you did not create an account, please ignore this email.

Best regards,
The Reliastra Team
        """.strip()

        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
    .container {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .header {{ background: #1a1a2e; color: white; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 22px; }}
    .body {{ padding: 32px; }}
    .body p {{ color: #333; line-height: 1.6; margin: 0 0 16px; }}
    .button {{ display: inline-block; background: #4361ee; color: white !important; text-decoration: none; padding: 12px 32px; border-radius: 8px; font-weight: 600; margin: 16px 0; }}
    .footer {{ padding: 20px 32px; background: #f9f9f9; text-align: center; font-size: 13px; color: #888; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Reliastra</h1>
    </div>
    <div class="body">
      <p>Hello <strong>{user_name}</strong>,</p>
      <p>Thank you for signing up. Please verify your email address to get started:</p>
      <p style="text-align: center;">
        <a href="{verification_url}" class="button">Verify Email Address</a>
      </p>
      <p style="font-size: 13px; color: #888;">
        This link expires in {EMAIL_VERIFICATION_EXPIRE_MINUTES} minutes. If you did not create an account, you can safely ignore this email.
      </p>
    </div>
    <div class="footer">
      <p>Reliastra — External Dependency Intelligence</p>
    </div>
  </div>
</body>
</html>
        """.strip()

        return plain, html

    def _render_reset_email(self, user_name: str, reset_url: str) -> tuple[str, str]:
        """Returns (plain_text, html_body) for password reset email."""
        plain = f"""
Hello {user_name},

We received a request to reset your Reliastra password. Click the link below to set a new password:

{reset_url}

This link expires in {PASSWORD_RESET_EXPIRE_MINUTES} minutes.

If you did not request a password reset, please ignore this email — your password will remain unchanged.

Best regards,
The Reliastra Team
        """.strip()

        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
    .container {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .header {{ background: #1a1a2e; color: white; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 22px; }}
    .body {{ padding: 32px; }}
    .body p {{ color: #333; line-height: 1.6; margin: 0 0 16px; }}
    .button {{ display: inline-block; background: #e63946; color: white !important; text-decoration: none; padding: 12px 32px; border-radius: 8px; font-weight: 600; margin: 16px 0; }}
    .footer {{ padding: 20px 32px; background: #f9f9f9; text-align: center; font-size: 13px; color: #888; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Reset Your Password</h1>
    </div>
    <div class="body">
      <p>Hello <strong>{user_name}</strong>,</p>
      <p>We received a request to reset your password. Click the button below to choose a new one:</p>
      <p style="text-align: center;">
        <a href="{reset_url}" class="button">Reset Password</a>
      </p>
      <p style="font-size: 13px; color: #888;">
        This link expires in {PASSWORD_RESET_EXPIRE_MINUTES} minutes. If you did not request a password reset, you can safely ignore this email — your password will not change.
      </p>
    </div>
    <div class="footer">
      <p>Reliastra — External Dependency Intelligence</p>
    </div>
  </div>
</body>
</html>
        """.strip()

        return plain, html

    # ── Email Verification ──────────────────────────────────────────

    async def send_verification_email(
        self, session: AsyncSession, email: str
    ) -> dict[str, Any]:
        """Generate a verification token and send the email."""
        user = await self.user_repository.get_by_email(session, email)
        if not user:
            raise ValidationException("No account found with this email address")

        if user.is_email_verified:
            raise AppException(
                "Email is already verified",
                status_code=400,
                code="EMAIL_ALREADY_VERIFIED",
            )

        # Invalidate any existing verification tokens
        await self.auth_repository.revoke_all_email_verification_tokens(
            session, user.id
        )

        # Generate new token
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=EMAIL_VERIFICATION_EXPIRE_MINUTES
        )
        await self.auth_repository.create_email_verification_token(
            session, user.id, token, expires_at
        )

        # Send email
        verification_url = self._build_verification_url(token)
        plain, html = self._render_verification_email(
            user.full_name, verification_url
        )
        email_client.send_email(
            to_email=email,
            subject="Verify your Reliastra email",
            body=plain,
            html_body=html,
        )

        logger.info("Verification email sent to %s", email)

        return {
            "message": "Verification email sent. Check your inbox.",
            "email": email,
        }

    async def verify_email(
        self, session: AsyncSession, token: str
    ) -> dict[str, Any]:
        """Verify a user's email using the token."""
        stored = await self.auth_repository.get_email_verification_token(
            session, token
        )

        if not stored:
            raise ValidationException(
                "Invalid verification token",
                details={"code": "INVALID_TOKEN"},
            )

        if stored.is_used:
            raise ValidationException(
                "This verification link has already been used",
                details={"code": "TOKEN_ALREADY_USED"},
            )

        if stored.expires_at < datetime.now(timezone.utc):
            raise ValidationException(
                "Verification link has expired. Please request a new one.",
                details={"code": "TOKEN_EXPIRED"},
            )

        # Mark token as used
        await self.auth_repository.mark_email_verification_used(session, token)

        # Mark user's email as verified
        user = await self.user_repository.get_by_id(session, stored.user_id)
        if user:
            await self.user_repository.update(
                session, user, is_email_verified=True
            )
            logger.info("Email verified for user %s", user.id)

        return {
            "message": "Email verified successfully.",
            "is_email_verified": True,
        }

    # ── Password Reset ─────────────────────────────────────────────

    async def send_password_reset_email(
        self, session: AsyncSession, email: str
    ) -> dict[str, Any]:
        """Generate a password reset token and send the email."""
        user = await self.user_repository.get_by_email(session, email)

        # Always return the same message to prevent email enumeration
        if not user:
            return {
                "message": "If an account with this email exists, a password reset link has been sent.",
            }

        # Invalidate any existing reset tokens
        await self.auth_repository.revoke_all_password_reset_tokens(
            session, user.id
        )

        # Generate new token
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=PASSWORD_RESET_EXPIRE_MINUTES
        )
        await self.auth_repository.create_password_reset_token(
            session, user.id, token, expires_at
        )

        # Send email
        reset_url = self._build_reset_url(token)
        plain, html = self._render_reset_email(user.full_name, reset_url)
        email_client.send_email(
            to_email=email,
            subject="Reset your Reliastra password",
            body=plain,
            html_body=html,
        )

        logger.info("Password reset email sent to %s", email)

        return {
            "message": "If an account with this email exists, a password reset link has been sent.",
        }

    async def reset_password(
        self, session: AsyncSession, token: str, new_password: str
    ) -> dict[str, Any]:
        """Reset a user's password using the token."""
        stored = await self.auth_repository.get_password_reset_token(
            session, token
        )

        if not stored:
            raise ValidationException(
                "Invalid password reset token",
                details={"code": "INVALID_TOKEN"},
            )

        if stored.is_used:
            raise ValidationException(
                "This reset link has already been used. Please request a new one.",
                details={"code": "TOKEN_ALREADY_USED"},
            )

        if stored.expires_at < datetime.now(timezone.utc):
            raise ValidationException(
                "Password reset link has expired. Please request a new one.",
                details={"code": "TOKEN_EXPIRED"},
            )

        # Mark token as used
        await self.auth_repository.mark_password_reset_used(session, token)

        # Update user's password
        password_hash = get_password_hash(new_password)
        user = await self.user_repository.get_by_id(session, stored.user_id)
        if user:
            await self.user_repository.update(
                session, user, password_hash=password_hash
            )
            # Revoke all refresh tokens (force re-login on all devices)
            logger.info("Password reset completed for user %s", user.id)

        return {
            "message": "Password has been reset successfully. You can now log in with your new password.",
        }


email_auth_service = EmailAuthService()
