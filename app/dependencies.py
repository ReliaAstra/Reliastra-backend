from __future__ import annotations

import logging
import uuid
from typing import Any, TYPE_CHECKING
from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ForbiddenException, ResourceNotFoundException, UnauthorizedException
from app.core.permissions import Role, has_permission
from app.core.security import decode_token
from app.db.session import get_db

if TYPE_CHECKING:
    from app.modules.organizations.models import Organization
    from app.modules.users.models import User

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)
# Use a custom header name to avoid conflict with HTTPBearer which also
# reads the "Authorization" header. Using "X-API-Key" allows both auth
# mechanisms to coexist without ambiguity.
security_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)

# Scopes that confer admin-level access (I-08).
_ADMIN_SCOPES = {"admin", "*", "write:*", "admin:*"}


def _api_key_role(scopes: list[str] | None) -> str:
    """Resolve an API key's effective role from its declared scopes.

    Empty/unrestricted keys retain full admin access for backward
    compatibility; keys that declare scopes only reach admin when a scope
    explicitly grants it.
    """
    scopes = scopes or []
    if not scopes:
        return Role.ADMIN.value
    if _ADMIN_SCOPES.intersection({s.lower() for s in scopes}):
        return Role.ADMIN.value
    return Role.MEMBER.value


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bearer: HTTPAuthorizationCredentials | None = Depends(security_bearer),
) -> User:
    from app.modules.api_keys.service import api_key_service
    from app.modules.organizations.repository import OrganizationRepository
    from app.modules.users.repository import UserRepository
    from app.modules.users.models import User

    auth_header = request.headers.get("authorization", "").strip()
    api_key_header = request.headers.get("x-api-key", "").strip()

    # Resolve the raw API key from either the X-API-Key header or an
    # Authorization header using one of the accepted schemes:
    #   Authorization: ApiKey rel_xxxxxxxx
    #   Authorization: Bearer rel_xxxxxxxx
    #   Authorization: rel_xxxxxxxx
    raw_key = api_key_header
    if not raw_key:
        auth_lower = auth_header.lower()
        for scheme in ("apikey ", "bearer "):
            if auth_lower.startswith(scheme):
                raw_key = auth_header.split(" ", 1)[1].strip()
                break
        else:
            if auth_lower.startswith("rel_"):
                raw_key = auth_header

    # API key authentication via X-API-Key header or "rel_" prefixed token
    if raw_key and raw_key.startswith("rel_"):
        api_key = await api_key_service.authenticate_key(db, raw_key)
        request.state.auth_method = "apikey"
        request.state.api_key_org_id = api_key.org_id
        request.state.api_key_scopes = api_key.scopes
        # Scope-aware role resolution (I-08): a key only attains admin/owner
        # level when its declared scopes explicitly grant it, instead of the
        # previous behaviour of unconditionally elevating every API key to ADMIN.
        request.state.current_role = _api_key_role(api_key.scopes)

        org_repo = OrganizationRepository()
        members = await org_repo.list_members(db, api_key.org_id)
        owner_member = next((m for m in members if m.role == Role.OWNER.value), members[0] if members else None)
        if owner_member:
            user = await UserRepository.get_by_id(db, owner_member.user_id)
            if user:
                return user

        return User(
            id=uuid.UUID(int=0),
            email="apikey@reliastra.local",
            full_name=f"API Key ({api_key.name})",
            is_active=True,
            is_superuser=False,
        )

    if bearer and bearer.credentials:
        payload = decode_token(bearer.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedException("Invalid token type")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise UnauthorizedException("Invalid token subject")

        user = await UserRepository.get_by_id(db, uuid.UUID(user_id_str))
        if not user or not user.is_active:
            raise UnauthorizedException("User not found or disabled")

        request.state.auth_method = "jwt"
        return user

    raise UnauthorizedException("Authentication required (Bearer token or X-API-Key header)")


async def get_current_org(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Organization:
    from app.modules.organizations.repository import OrganizationRepository

    org_id_val: uuid.UUID | None = None

    if "org_id" in request.path_params:
        try:
            org_id_val = uuid.UUID(str(request.path_params["org_id"]))
        except ValueError as exc:
            raise ResourceNotFoundException("Invalid organization ID format") from exc
    elif request.headers.get("x-organization-id"):
        try:
            org_id_val = uuid.UUID(request.headers["x-organization-id"])
        except ValueError as exc:
            raise ResourceNotFoundException("Invalid X-Organization-ID header") from exc

    org_repo = OrganizationRepository()

    if getattr(request.state, "auth_method", "") == "apikey":
        api_key_org_id = getattr(request.state, "api_key_org_id", None)
        if org_id_val and org_id_val != api_key_org_id:
            raise ForbiddenException("API key is not authorized for this organization")
        org_id_val = api_key_org_id

        org = await org_repo.get_by_id(db, org_id_val)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        # Preserve the scope-derived role rather than re-elevating to ADMIN.
        request.state.current_role = _api_key_role(
            getattr(request.state, "api_key_scopes", None)
        )
        return org

    if org_id_val:
        member = await org_repo.get_member(db, org_id_val, current_user.id)
        if not member:
            raise ForbiddenException("User is not a member of this organization")
        org = await org_repo.get_by_id(db, org_id_val)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        request.state.current_role = member.role
        return org

    orgs = await org_repo.list_for_user(db, current_user.id)
    if not orgs:
        raise ResourceNotFoundException("User does not belong to any organization")
    org = orgs[0]
    member = await org_repo.get_member(db, org.id, current_user.id)
    request.state.current_role = member.role if member else Role.VIEWER.value
    return org


def require_role(min_role: Role) -> Any:
    async def role_checker(
        request: Request,
        current_org: Organization = Depends(get_current_org),
    ) -> Organization:
        user_role = getattr(request.state, "current_role", Role.VIEWER.value)
        if not has_permission(user_role, min_role.value):
            raise ForbiddenException(
                f"Action requires at least '{min_role.value}' role, but user has '{user_role}' role."
            )
        return current_org

    return role_checker


require_owner = require_role(Role.OWNER)
require_admin = require_role(Role.ADMIN)
require_member = require_role(Role.MEMBER)
require_viewer = require_role(Role.VIEWER)
