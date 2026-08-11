"""Authentication API contracts."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.organizations.schemas import OrganizationResponse
from app.modules.users.schemas import UserResponse


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_password_strength(self) -> RegisterRequest:
        classes = [
            any(c.islower() for c in self.password),
            any(c.isupper() for c in self.password),
            any(c.isdigit() for c in self.password),
        ]
        if sum(classes) < 2:
            raise ValueError(
                "Password must contain at least two of lowercase, uppercase, and digits"
            )
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int


class RegistrationResponse(BaseModel):
    user: UserResponse
    organization: OrganizationResponse
    tokens: TokenResponse
