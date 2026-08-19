import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator
from app.modules.auth.constants import TOKEN_TYPE_BEARER


class RegisterRequest(BaseModel):
    email: EmailStr
    # FIX 33: minimum password length is enforced at the schema level so
    # OpenAPI advertises it and short passwords are rejected before hashing.
    password: str = Field(min_length=8, max_length=128)
    full_name: str
    org_name: str | None = None
    #: Referral code captured from ``https://reliastra.com/r/{code}`` and
    #: replayed at signup. Links the new account to the referring partner.
    ref_code: str | None = Field(default=None, max_length=32)


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


class RegisterResponse(BaseModel):
    """Single-step signup payload: user + default org + tokens."""

    user: "UserResponseLite"
    organization: "OrganizationLite"
    tokens: TokenResponse


class UserResponseLite(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool = True


class OrganizationLite(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str


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
    # FIX 33: minimum password length enforced at the schema level.
    new_password: str = Field(min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    message: str
