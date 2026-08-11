import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None


class UserInternalDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    password_hash: str
    full_name: str
    is_active: bool
    is_superuser: bool
