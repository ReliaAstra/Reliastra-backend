from pydantic import BaseModel, EmailStr
from app.modules.auth.constants import TOKEN_TYPE_BEARER


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    org_name: str | None = None


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
