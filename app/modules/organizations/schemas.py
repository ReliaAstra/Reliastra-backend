"""Organization request, response, and internal DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.organizations.constants import MemberRole, Plan


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    billing_email: EmailStr | None = None


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    billing_email: EmailStr | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    plan: Plan
    billing_email: EmailStr | None
    created_at: datetime
    updated_at: datetime


class MemberInviteRequest(BaseModel):
    email: EmailStr
    role: MemberRole = MemberRole.MEMBER


class MemberRoleUpdateRequest(BaseModel):
    role: MemberRole


class MemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str
    role: MemberRole
    joined_at: datetime


class MembershipDTO(BaseModel):
    org_id: UUID
    user_id: UUID
    role: MemberRole
