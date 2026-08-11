"""Dependency configuration policy and scheduler interface."""

from __future__ import annotations

import builtins
from datetime import datetime
from uuid import UUID

from app.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.core.pagination import Page
from app.core.security import decrypt_json, encrypt_json
from app.modules.dependencies.constants import PLAN_DEPENDENCY_LIMIT, PLAN_MIN_INTERVAL
from app.modules.dependencies.repository import DependencyRepository
from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
    DependencyExecutionDTO,
    DependencyResponse,
    DependencyScheduleDTO,
    DependencyUpdateRequest,
)
from app.modules.organizations.constants import Plan
from app.modules.organizations.service import OrganizationService


class DependencyService:
    def __init__(
        self,
        repository: DependencyRepository,
        organizations: OrganizationService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.organizations = organizations
        self.settings = settings

    async def create(self, org_id: UUID, request: DependencyCreateRequest) -> DependencyResponse:
        organization = await self.organizations.get(org_id)
        if await self.repository.count(org_id) >= PLAN_DEPENDENCY_LIMIT[organization.plan]:
            raise AppError(
                "Dependency limit reached for the current plan", {"plan": organization.plan.value}
            )
        values = request.model_dump(mode="python")
        values["endpoint_url"] = str(request.endpoint_url)
        values["check_interval_seconds"] = self._validated_interval(
            request.check_interval_seconds, organization.plan
        )
        values["headers"] = (
            encrypt_json(request.headers, self.settings.secret_key.get_secret_value())
            if request.headers
            else None
        )
        values["org_id"] = org_id
        return DependencyResponse.model_validate(await self.repository.create(values))

    async def list(self, org_id: UUID, limit: int, cursor: UUID | None) -> Page[DependencyResponse]:
        models = await self.repository.list(org_id, limit, cursor)
        has_more = len(models) > limit
        items = [DependencyResponse.model_validate(model) for model in models[:limit]]
        return Page(items=items, next_cursor=items[-1].id if has_more else None)

    async def get(self, org_id: UUID, dependency_id: UUID) -> DependencyResponse:
        model = await self.repository.get(org_id, dependency_id)
        if model is None:
            raise NotFoundError("Dependency not found")
        return DependencyResponse.model_validate(model)

    async def update(
        self, org_id: UUID, dependency_id: UUID, request: DependencyUpdateRequest
    ) -> DependencyResponse:
        model = await self.repository.get(org_id, dependency_id)
        if model is None:
            raise NotFoundError("Dependency not found")
        values = request.model_dump(exclude_unset=True, mode="python")
        if request.endpoint_url is not None:
            values["endpoint_url"] = str(request.endpoint_url)
        if "headers" in values and request.headers is not None:
            values["headers"] = encrypt_json(
                request.headers, self.settings.secret_key.get_secret_value()
            )
        if request.check_interval_seconds is not None:
            organization = await self.organizations.get(org_id)
            values["check_interval_seconds"] = self._validated_interval(
                request.check_interval_seconds, organization.plan
            )
        return DependencyResponse.model_validate(await self.repository.update(model, values))

    async def delete(self, org_id: UUID, dependency_id: UUID) -> None:
        model = await self.repository.get(org_id, dependency_id)
        if model is None:
            raise NotFoundError("Dependency not found")
        from app.db.base import utc_now

        await self.repository.update(model, {"deleted_at": utc_now(), "is_active": False})

    async def execution_config(self, dependency_id: UUID) -> DependencyExecutionDTO:
        model = await self.repository.get_any_org(dependency_id)
        if model is None:
            raise NotFoundError("Dependency not found")
        return DependencyExecutionDTO(
            id=model.id,
            org_id=model.org_id,
            endpoint_url=model.endpoint_url,
            method=model.method,
            headers=decrypt_json(model.headers, self.settings.secret_key.get_secret_value()),
            expected_status_codes=model.expected_status_codes,
            timeout_seconds=model.timeout_seconds,
            regions=model.regions,
            alert_threshold_ms=model.alert_threshold_ms,
        )

    async def claim_due(self, now: datetime) -> builtins.list[DependencyScheduleDTO]:
        models = await self.repository.claim_due(now)
        return [
            DependencyScheduleDTO.model_validate(model, from_attributes=True) for model in models
        ]

    @staticmethod
    def _validated_interval(requested: int | None, plan: Plan) -> int:
        minimum = PLAN_MIN_INTERVAL[plan]
        if requested is not None and requested < minimum:
            raise AppError(
                "Check interval is below the current plan minimum", {"minimum_seconds": minimum}
            )
        return requested or minimum
