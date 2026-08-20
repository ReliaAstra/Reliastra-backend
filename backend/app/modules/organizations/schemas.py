import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.core.permissions import Plan, Role


class OrganizationCreateRequest(BaseModel):
    name: str
    # FIX 34: slug validation — lowercase letters, digits and hyphens only.
    slug: str | None = Field(
        default=None, pattern=r"^[a-z0-9-]+$", min_length=1, max_length=50
    )


class OrganizationUpdateRequest(BaseModel):
    name: str | None = None
    # NOTE: Plan changes are NOT allowed here. Plan upgrades/downgrades
    # must go through the billing service (verify_transaction / webhook).
    # An org admin setting ``plan: \"professional\"`` via PATCH would bypass
    # payment entirely — see P0-2 security audit finding.


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    plan: str
    has_agency_mode: bool = False
    created_at: datetime
    updated_at: datetime


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
