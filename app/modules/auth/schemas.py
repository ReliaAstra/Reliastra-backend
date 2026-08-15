import uuid

from pydantic import BaseModel, EmailStr, field_validator
from app.modules.auth.constants import TOKEN_TYPE_BEARER


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    org_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = TOKEN_TYPE_BEARER
    expires_in: int


class GoogleAuthUrlResponse(BaseModel):
    authorization_url: str
    state: str


class GoogleAuthRequest(BaseModel):
    code: str
    state: str | None = None


class GitHubAuthUrlResponse(BaseModel):
    authorization_url: str
    state: str


class GitHubAuthRequest(BaseModel):
    code: str
    state: str | None = None


class OAuthAuthResponse(TokenResponse):
    """Shared response for both Google and GitHub OAuth."""

    is_new_user: bool = False
    user_id: uuid.UUID
    email: str
    full_name: str


# Aliases so existing Google code still works
GoogleAuthResponse = OAuthAuthResponse
GitHubAuthResponse = OAuthAuthResponse


# ── Email Verification ─────────────────────────────────────────────


class SendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class VerifyEmailResponse(BaseModel):
    message: str
    is_email_verified: bool


# ── Password Reset ─────────────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class ResetPasswordResponse(BaseModel):
    message: str
