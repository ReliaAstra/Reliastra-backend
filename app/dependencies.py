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


def _infer_scope(request: Request) -> str | None:
    """Map organization API routes to their programmatic access scope."""
    path = request.url.path
    write = request.method not in {"GET", "HEAD", "OPTIONS"}
    mappings = (
        ("/evidence", "evidence"),
        ("/dependencies", "dependencies"),
        ("/checks", "checks"),
        ("/incidents", "incidents"),
        ("/billing", "billing"),
        ("/notifications", "notifications"),
        ("/api-keys", "api_keys"),
    )
    for marker, resource in mappings:
        if marker in path:
            # Evidence currently exposes read/regeneration but has no write scope.
            action = "read" if resource == "evidence" else "write" if write else "read"
            return f"{action}:{resource}"
    if any(marker in path for marker in ("/clients", "/ai-providers")):
        return f"{'write' if write else 'read'}:organizations"
    if "/dashboard/" in path:
        return "read:checks"
    if path.startswith("/v1/orgs"):
        return f"{'write' if write else 'read'}:organizations"
    return None


def _has_scope(scopes: list[str], required_scope: str) -> bool:
    if required_scope in scopes or "*" in scopes:
        return True
    action, _, resource = required_scope.partition(":")
    # A write grant implies read access to the same resource.
    return action == "read" and f"write:{resource}" in scopes


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

    # API key authentication supports X-API-Key, a raw rel_ Authorization
    # value, or the conventional `Authorization: ApiKey rel_...` form.
    raw_key: str | None = api_key_header or None
    if not raw_key and auth_header.lower().startswith("rel_"):
        raw_key = auth_header
    if (
        not raw_key
        and bearer
        and bearer.credentials.startswith("rel_")
        and bearer.scheme.lower() in {"apikey", "bearer"}
    ):
        raw_key = bearer.credentials
    if not raw_key and auth_header.lower().startswith("apikey "):
        raw_key = auth_header.split(None, 1)[1].strip()

    if raw_key:
        from app.core.rate_limit import api_key_limiter, enforce_rate_limit

        await enforce_rate_limit(
            request,
            api_key_limiter,
            identifier=raw_key[:8] if len(raw_key) >= 8 else raw_key,
        )
        api_key = await api_key_service.authenticate_key(db, raw_key)
        request.state.auth_method = "apikey"
        request.state.api_key_org_id = api_key.org_id
        request.state.api_key_scopes = api_key.scopes
        request.state.current_role = Role.ADMIN.value
        # FIX 7/36: authenticated principal for idempotency scoping & tracing.
        request.state.user_id = f"apikey:{api_key.id}"

        required_scope = getattr(request.state, "required_scope", None)
        required_scope = required_scope or _infer_scope(request)
        if required_scope and not _has_scope(api_key.scopes, required_scope):
            raise ForbiddenException(
                f"API key lacks required scope: {required_scope}"
            )

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
        # FIX 7/36: authenticated principal for idempotency scoping & tracing.
        request.state.user_id = str(user.id)
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
        request.state.current_role = Role.ADMIN.value
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


def require_scope(scope: str) -> Any:
    """Require an API-key scope while leaving JWT users governed by RBAC."""

    async def scope_checker(
        request: Request,
        current_org: Organization = Depends(get_current_org),
    ) -> Organization:
        if getattr(request.state, "auth_method", "") == "apikey":
            scopes = getattr(request.state, "api_key_scopes", [])
            if not _has_scope(scopes, scope):
                raise ForbiddenException(
                    f"API key lacks required scope: {scope}"
                )
        return current_org

    return scope_checker


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

