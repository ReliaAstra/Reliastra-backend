import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)
from app.core.permissions import get_dependency_limit, get_min_check_interval
from app.core.security import decrypt_jsonb, encrypt_jsonb
from app.modules.dependencies.models import Dependency
from app.modules.dependencies.repository import DependencyRepository
from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
    DependencyHistoryResponse,
    DependencyInternalDTO,
    DependencyResponse,
    DependencyUpdateRequest,
)
from app.modules.organizations.repository import OrganizationRepository


class DependencyService:
    def __init__(
        self,
        repository: DependencyRepository = DependencyRepository(),
        org_repository: OrganizationRepository = OrganizationRepository(),
    ) -> None:
        self.repository = repository
        self.org_repository = org_repository

    @staticmethod
    def _encode_headers(headers: dict[str, Any] | None) -> dict[str, Any] | None:
        if not headers:
            return None
        encrypted_str = encrypt_jsonb(headers)
        return {"_encrypted_data": encrypted_str}

    @staticmethod
    def _decode_headers(headers: dict[str, Any] | None) -> dict[str, Any] | None:
        if not headers:
            return None
        if "_encrypted_data" in headers:
            return decrypt_jsonb(str(headers["_encrypted_data"]))
        return headers

    def _to_response(self, dep: Dependency) -> DependencyResponse:
        # FIX 23: never return decrypted headers to API consumers. Expose only
        # the presence flag; the plaintext stays encrypted at rest and is
        # decoded exclusively server-side (get_dependency_config_internal).
        response_dict = DependencyResponse.model_validate(dep).model_dump()
        response_dict["headers"] = None
        response_dict["has_headers"] = bool(dep.headers)
        return DependencyResponse.model_validate(response_dict)

    async def list_dependencies(
        self, session: AsyncSession, org_id: uuid.UUID, limit: int = 50
    ) -> list[DependencyResponse]:
        deps = await self.repository.list_for_org(session, org_id, limit=limit)
        return [self._to_response(dep) for dep in deps]

    async def create_dependency(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: DependencyCreateRequest,
    ) -> DependencyResponse:
        org = await self.org_repository.get_by_id(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        min_interval = get_min_check_interval(org.plan)
        if request.check_interval_seconds < min_interval:
            raise ValidationException(
                f"Minimum check interval for plan '{org.plan}' is {min_interval} seconds."
            )

        max_deps = get_dependency_limit(org.plan)
        current_count = await self.repository.count_for_org(session, org_id)
        if current_count >= max_deps:
            raise ConflictException(
                f"Dependency limit reached for plan '{org.plan}' ({max_deps})."
            )

        from app.modules.agencies.repository import AgencyRepository

        application_id = request.application_id
        if application_id:
            application = await AgencyRepository.get_application(
                session, application_id
            )
            if not application or application.org_id != org_id:
                raise ValidationException(
                    "Application does not belong to this organization"
                )
        else:
            application = await AgencyRepository.get_default_application(
                session, org_id
            )
            if not application:
                application = await AgencyRepository.create_application(
                    session,
                    org_id=org_id,
                    name="Default",
                    description="Default application",
                )
            application_id = application.id

        encoded_headers = self._encode_headers(request.headers)
        dep = await self.repository.create(
            session=session,
            org_id=org_id,
            application_id=application_id,
            name=request.name,
            endpoint_url=request.endpoint_url,
            method=request.method.value,
            headers=encoded_headers,
            expected_status_codes=request.expected_status_codes,
            timeout_seconds=request.timeout_seconds,
            check_interval_seconds=request.check_interval_seconds,
            regions=request.regions,
            alert_threshold_ms=request.alert_threshold_ms,
            is_active=request.is_active,
        )
        return self._to_response(dep)

    async def get_dependency(
        self, session: AsyncSession, org_id: uuid.UUID, dep_id: uuid.UUID
    ) -> DependencyResponse:
        dep = await self.repository.get_by_id(session, dep_id)
        if not dep or dep.org_id != org_id:
            raise ResourceNotFoundException("Dependency not found")
        return self._to_response(dep)

    async def update_dependency(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        dep_id: uuid.UUID,
        request: DependencyUpdateRequest,
    ) -> DependencyResponse:
        dep = await self.repository.get_by_id(session, dep_id)
        if not dep or dep.org_id != org_id:
            raise ResourceNotFoundException("Dependency not found")

        org = await self.org_repository.get_by_id(session, org_id)
        if org and request.check_interval_seconds is not None:
            min_interval = get_min_check_interval(org.plan)
            if request.check_interval_seconds < min_interval:
                raise ValidationException(
                    f"Minimum check interval for plan '{org.plan}' is {min_interval} seconds."
                )

        update_kwargs: dict[str, Any] = {}
        if request.application_id is not None:
            from app.modules.agencies.repository import AgencyRepository

            application = await AgencyRepository.get_application(
                session, request.application_id
            )
            if not application or application.org_id != org_id:
                raise ValidationException(
                    "Application does not belong to this organization"
                )
            update_kwargs["application_id"] = request.application_id

        for field in [
            "name",
            "endpoint_url",
            "method",
            "expected_status_codes",
            "timeout_seconds",
            "check_interval_seconds",
            "regions",
            "alert_threshold_ms",
            "is_active",
        ]:
            val = getattr(request, field, None)
            if val is not None:
                if field == "method" and hasattr(val, "value"):
                    update_kwargs[field] = val.value
                else:
                    update_kwargs[field] = val
        if request.headers is not None:
            update_kwargs["headers"] = self._encode_headers(request.headers)

        updated = await self.repository.update(session, dep, **update_kwargs)
        return self._to_response(updated)

    async def delete_dependency(
        self, session: AsyncSession, org_id: uuid.UUID, dep_id: uuid.UUID
    ) -> None:
        dep = await self.repository.get_by_id(session, dep_id)
        if not dep or dep.org_id != org_id:
            raise ResourceNotFoundException("Dependency not found")
        await self.repository.soft_delete(session, dep)

    async def get_dependency_history(
        self, session: AsyncSession, org_id: uuid.UUID, dep_id: uuid.UUID
    ) -> DependencyHistoryResponse:
        dep = await self.repository.get_by_id(session, dep_id)
        if not dep or dep.org_id != org_id:
            raise ResourceNotFoundException("Dependency not found")

        # Delegate to check repository for aggregated stats
        from app.modules.checks.repository import CheckRepository
        stats = await CheckRepository.get_aggregated_stats(session, dep_id)
        return DependencyHistoryResponse(
            dependency_id=dep_id,
            uptime_percentage=stats.get("uptime_percentage", 100.0),
            avg_latency_ms=stats.get("avg_latency_ms", 0.0),
            total_checks=stats.get("total_checks", 0),
            total_up=stats.get("total_up", 0),
            total_down=stats.get("total_down", 0),
        )

    async def get_dependency_config_internal(
        self, session: AsyncSession, dep_id: uuid.UUID, org_id: uuid.UUID | None = None
    ) -> DependencyInternalDTO | None:
        dep = await self.repository.get_by_id(session, dep_id)
        if not dep:
            return None
        if org_id is not None and dep.org_id != org_id:
            logger.warning("Cross-tenant config access attempt dep=%s caller_org=%s", dep_id, org_id)
            return None
        dto_dict = DependencyInternalDTO.model_validate(dep).model_dump()
        dto_dict["headers"] = self._decode_headers(dep.headers)
        return DependencyInternalDTO.model_validate(dto_dict)


dependency_service = DependencyService()
