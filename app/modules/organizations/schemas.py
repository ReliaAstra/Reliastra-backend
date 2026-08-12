import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr
from app.core.permissions import Plan, Role


class OrganizationCreateRequest(BaseModel):
    name: str
    slug: str | None = None


class OrganizationUpdateRequest(BaseModel):
    name: str | None = None
    plan: Plan | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    plan: str
    created_at: datetime
    updated_at: datetime


class OrganizationInternalResponse(OrganizationResponse):
    """Internal-only response that includes Stripe billing identifiers."""
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None


class OrganizationMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime


class OrganizationMemberInviteRequest(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


class OrganizationMemberRoleUpdateRequest(BaseModel):
    role: Role
