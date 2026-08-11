"""FastAPI dependency injection and worker-side service composition."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated, Any, cast
from uuid import UUID

import jwt
from fastapi import Depends, Header, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.permissions import Role, ensure_role
from app.core.security import decode_token
from app.db.session import DatabaseManager


class Principal(BaseModel):
    user_id: UUID | None = None
    api_key_id: UUID | None = None
    api_key_org_id: UUID | None = None
    scopes: set[str] = Field(default_factory=set)

    def require_user_id(self) -> UUID:
        if self.user_id is None:
            raise ForbiddenError("This operation requires interactive user authentication")
        return self.user_id


@dataclass(frozen=True)
class OrgContext:
    org_id: UUID
    role: Role
    principal: Principal


class CeleryTaskDispatcher:
    def send(self, task: str, *args: object) -> None:
        from app.infrastructure.celery_app import celery_app

        celery_app.send_task(task, args=list(args))


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    database: DatabaseManager = request.app.state.database
    async for session in database.session():
        yield session


async def get_replica_db(request: Request) -> AsyncIterator[AsyncSession]:
    database: DatabaseManager = request.app.state.database
    async for session in database.replica_session():
        yield session


def get_user_service(session: AsyncSession = Depends(get_db)) -> Any:
    from app.modules.users.repository import UserRepository
    from app.modules.users.service import UserService

    return UserService(UserRepository(session))


def get_org_service(session: AsyncSession = Depends(get_db)) -> Any:
    return build_organization_service(session)


def get_auth_service(
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_db),
) -> Any:
    from app.modules.auth.repository import AuthRepository
    from app.modules.auth.service import AuthService
    from app.modules.users.repository import UserRepository
    from app.modules.users.service import UserService

    users = UserService(UserRepository(session))
    organizations = build_organization_service(session)
    return AuthService(AuthRepository(redis), users, organizations, settings)


def get_api_key_service(session: AsyncSession = Depends(get_db)) -> Any:
    from app.modules.api_keys.repository import ApiKeyRepository
    from app.modules.api_keys.service import ApiKeyService

    return ApiKeyService(ApiKeyRepository(session))


async def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
    users: Any = Depends(get_user_service),
    api_keys: Any = Depends(get_api_key_service),
) -> Principal:
    if not authorization:
        raise UnauthorizedError("Authorization header is required")
    if authorization.startswith("Bearer "):
        try:
            claims = decode_token(
                authorization[7:], settings.secret_key.get_secret_value(), "access"
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid or expired access token") from exc
        user = await users.get(claims.sub)
        if not user.is_active:
            raise UnauthorizedError("User account is inactive")
        return Principal(user_id=user.id)
    if authorization.startswith("ApiKey "):
        identity = await api_keys.authenticate(authorization[7:])
        return Principal(
            api_key_id=identity.id,
            api_key_org_id=identity.org_id,
            scopes=set(identity.scopes),
        )
    raise UnauthorizedError("Authorization must use Bearer or ApiKey scheme")


def org_context(required_role: Role) -> Callable[..., object]:
    async def dependency(
        request: Request,
        principal: Principal = Depends(get_current_principal),
        organizations: Any = Depends(get_org_service),
        x_organization_id: Annotated[UUID | None, Header()] = None,
    ) -> OrgContext:
        path_id = request.path_params.get("org_id")
        org_id = UUID(path_id) if path_id else x_organization_id
        if org_id is None and principal.user_id:
            available = await organizations.list_for_user(principal.user_id)
            org_id = available[0].id if available else None
        if org_id is None:
            raise ForbiddenError("Organization context is required")
        if principal.api_key_id:
            if principal.api_key_org_id != org_id:
                raise ForbiddenError("API key is not valid for this organization")
            _ensure_api_scope(principal.scopes, request.method, request.url.path)
            actual = Role.MEMBER
        else:
            membership = await organizations.membership(org_id, principal.require_user_id())
            if membership is None:
                raise ForbiddenError("You are not a member of this organization")
            actual = Role(membership.role.value)
        ensure_role(actual, required_role)
        return OrgContext(org_id=org_id, role=actual, principal=principal)

    return dependency


def _ensure_api_scope(scopes: set[str], method: str, path: str) -> None:
    mutating = method in {"POST", "PATCH", "DELETE"}
    if "/dependencies" in path and ("/results" in path or "/history" in path):
        required = "read:checks"
    elif "/dependencies" in path:
        required = "write:dependencies" if mutating else "read:dependencies"
    elif "/incidents" in path and path.endswith("/evidence"):
        required = "generate:evidence"
    elif "/incidents" in path:
        required = "write:incidents" if mutating else "read:incidents"
    elif "/evidence" in path:
        required = "generate:evidence" if mutating else "read:evidence"
    elif "/notifications" in path:
        required = "manage:notifications"
    elif "/dashboard" in path:
        required = "read:dashboard"
    else:
        required = "read:organization"
    if required not in scopes:
        raise ForbiddenError(f"API key is missing scope '{required}'")


def build_organization_service(session: AsyncSession) -> Any:
    from app.modules.organizations.repository import OrganizationRepository
    from app.modules.organizations.service import OrganizationService
    from app.modules.users.repository import UserRepository
    from app.modules.users.service import UserService

    return OrganizationService(
        OrganizationRepository(session), UserService(UserRepository(session))
    )


def build_dependency_service(session: AsyncSession, settings: Settings) -> Any:
    from app.modules.dependencies.repository import DependencyRepository
    from app.modules.dependencies.service import DependencyService

    return DependencyService(
        DependencyRepository(session), build_organization_service(session), settings
    )


def build_check_service(
    session: AsyncSession, settings: Settings, dispatcher: Any | None = None
) -> Any:
    from app.modules.checks.repository import CheckRepository
    from app.modules.checks.service import CheckService

    return CheckService(
        CheckRepository(session), build_dependency_service(session, settings), dispatcher
    )


def build_incident_service(
    session: AsyncSession, settings: Settings, dispatcher: Any | None = None
) -> Any:
    from app.modules.incidents.repository import IncidentRepository
    from app.modules.incidents.service import IncidentService

    return IncidentService(
        IncidentRepository(session),
        build_dependency_service(session, settings),
        dispatcher,
        build_organization_service(session),
    )


def build_evidence_repository(session: AsyncSession) -> Any:
    from app.modules.evidence.repository import EvidenceRepository

    return EvidenceRepository(session)


def build_notification_service(session: AsyncSession, settings: Settings) -> Any:
    from app.infrastructure.email import EmailClient
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.notifications.service import NotificationService

    email = EmailClient(settings.smtp_host, settings.smtp_port, settings.smtp_from)
    return NotificationService(NotificationRepository(session), email)


def _storage(settings: Settings) -> Any:
    from app.infrastructure.storage import ObjectStorage

    return ObjectStorage(
        settings.minio_endpoint,
        settings.minio_access_key.get_secret_value(),
        settings.minio_secret_key.get_secret_value(),
        settings.minio_bucket,
        settings.minio_use_ssl,
    )


def get_dependency_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    return build_dependency_service(session, settings)


def get_check_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    return build_check_service(session, settings)


def get_incident_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    return build_incident_service(session, settings, CeleryTaskDispatcher())


def get_evidence_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    from app.modules.evidence.repository import EvidenceRepository
    from app.modules.evidence.service import EvidenceService

    return EvidenceService(
        EvidenceRepository(session),
        build_incident_service(session, settings),
        build_organization_service(session),
        _storage(settings),
        CeleryTaskDispatcher(),
    )


def get_notification_service(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    return build_notification_service(session, settings)


def get_vendor_service(
    session: AsyncSession = Depends(get_replica_db),
    redis: Redis = Depends(get_redis),
) -> Any:
    from app.modules.vendors.repository import VendorRepository
    from app.modules.vendors.service import VendorService

    return VendorService(VendorRepository(session), redis)


def get_dashboard_service(
    session: AsyncSession = Depends(get_db),
    replica: AsyncSession = Depends(get_replica_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> Any:
    from app.modules.checks.repository import CheckRepository
    from app.modules.checks.service import CheckService
    from app.modules.dashboard.repository import DashboardRepository
    from app.modules.dashboard.service import DashboardService
    from app.modules.incidents.repository import IncidentRepository
    from app.modules.incidents.service import IncidentService
    from app.modules.vendors.repository import VendorRepository
    from app.modules.vendors.service import VendorService

    dependencies = build_dependency_service(session, settings)
    checks = CheckService(CheckRepository(replica), dependencies)
    incidents = IncidentService(IncidentRepository(replica), dependencies)
    vendors = VendorService(VendorRepository(replica), redis)
    return DashboardService(DashboardRepository(replica), dependencies, checks, incidents, vendors)
