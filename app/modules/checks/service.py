"""Protocol registry, HTTP execution, result recording, and quorum logic."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import httpx

from app.core.pagination import Page
from app.modules.checks.constants import (
    FAILURE_QUORUM,
    FAILURE_WINDOW_SECONDS,
    RECOVERY_CONSECUTIVE_CHECKS,
    RECOVERY_QUORUM,
)
from app.modules.checks.repository import CheckRepository
from app.modules.checks.schemas import (
    CheckResultCreateDTO,
    CheckResultResponse,
    DependencyHistoryResponse,
)
from app.modules.dependencies.schemas import DependencyExecutionDTO
from app.modules.dependencies.service import DependencyService
from app.modules.notifications.schemas import AlertPayload


class TaskDispatcher(Protocol):
    def send(self, task: str, *args: object) -> None: ...


class ResultState(Protocol):
    region: str
    is_up: bool


class CheckProtocol(ABC):
    @abstractmethod
    async def execute(
        self, config: DependencyExecutionDTO, region: str
    ) -> CheckResultCreateDTO: ...


class HttpCheckProtocol(CheckProtocol):
    async def execute(self, config: DependencyExecutionDTO, region: str) -> CheckResultCreateDTO:
        started = time.perf_counter()
        status_code: int | None = None
        error: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=config.timeout_seconds, follow_redirects=True
            ) as client:
                response = await client.request(
                    config.method.value, config.endpoint_url, headers=config.headers
                )
                status_code = response.status_code
                is_up = status_code in config.expected_status_codes
                if not is_up:
                    error = f"Unexpected HTTP status {status_code}"
        except httpx.HTTPError as exc:
            is_up = False
            error = f"{type(exc).__name__}: {exc}"[:2000]
        latency = (time.perf_counter() - started) * 1000
        return CheckResultCreateDTO(
            dependency_id=config.id,
            org_id=config.org_id,
            region=region,
            executed_at=datetime.now(UTC),
            latency_ms=latency,
            status_code=status_code,
            is_up=is_up,
            error_message=error,
        )


class CheckService:
    def __init__(
        self,
        repository: CheckRepository,
        dependencies: DependencyService,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.repository = repository
        self.dependencies = dependencies
        self.dispatcher = dispatcher
        self.protocols: dict[str, CheckProtocol] = {"http": HttpCheckProtocol()}

    def register_protocol(self, name: str, protocol: CheckProtocol) -> None:
        self.protocols[name] = protocol

    async def execute(self, dependency_id: UUID, region: str) -> CheckResultResponse:
        config = await self.dependencies.execution_config(dependency_id)
        result = await self.protocols["http"].execute(config, region)
        model = await self.repository.create(result)
        recent = await self.repository.recent(
            dependency_id, result.executed_at - timedelta(seconds=FAILURE_WINDOW_SECONDS)
        )
        if config.alert_threshold_ms and result.latency_ms > config.alert_threshold_ms:
            previous = [item for item in recent if item.id != model.id]
            was_breached = any(item.latency_ms > config.alert_threshold_ms for item in previous)
            if self.dispatcher and not was_breached:
                payload = AlertPayload(
                    org_id=config.org_id,
                    severity="minor",
                    title="Dependency latency threshold exceeded",
                    body=(
                        f"{config.endpoint_url} responded in {result.latency_ms:.1f}ms; "
                        f"threshold is {config.alert_threshold_ms}ms."
                    ),
                    metadata={
                        "dependency_id": str(config.id),
                        "region": region,
                        "latency_ms": result.latency_ms,
                    },
                )
                self.dispatcher.send("notifications.dispatch", payload.model_dump(mode="json"))
        if (
            not result.is_up
            and len({item.region for item in recent if not item.is_up}) >= FAILURE_QUORUM
        ):
            await self.repository.set_quorum(model)
            if self.dispatcher:
                self.dispatcher.send("incidents.create_incident", str(dependency_id))
        elif result.is_up and self._recovery_confirmed(recent):
            if self.dispatcher:
                self.dispatcher.send("incidents.resolve_incident", str(dependency_id))
        return CheckResultResponse.model_validate(model)

    async def list_results(
        self,
        org_id: UUID,
        dependency_id: UUID,
        start: datetime,
        end: datetime,
        limit: int,
        cursor: UUID | None,
    ) -> Page[CheckResultResponse]:
        await self.dependencies.get(org_id, dependency_id)
        models = await self.repository.list(org_id, dependency_id, start, end, limit, cursor)
        has_more = len(models) > limit
        items = [CheckResultResponse.model_validate(item) for item in models[:limit]]
        return Page(items=items, next_cursor=items[-1].id if has_more else None)

    async def evidence_results(
        self, org_id: UUID, dependency_id: UUID, start: datetime, end: datetime
    ) -> list[CheckResultResponse]:
        await self.dependencies.get(org_id, dependency_id)
        models = await self.repository.list(org_id, dependency_id, start, end, 10_000, None)
        return [CheckResultResponse.model_validate(item) for item in models[:10_000]]

    async def history(
        self, org_id: UUID, dependency_id: UUID, start: datetime, end: datetime
    ) -> DependencyHistoryResponse:
        await self.dependencies.get(org_id, dependency_id)
        points = await self.repository.history(org_id, dependency_id, start, end)
        return DependencyHistoryResponse(
            dependency_id=dependency_id, from_time=start, to_time=end, points=points
        )

    async def org_uptime(self, org_id: UUID, start: datetime) -> float:
        _checks, uptime = await self.repository.org_summary(org_id, start)
        return uptime

    @staticmethod
    def _recovery_confirmed(results: Sequence[ResultState]) -> bool:
        by_region: dict[str, list[ResultState]] = {}
        for result in results:
            by_region.setdefault(result.region, []).append(result)
        recovered = sum(
            1
            for values in by_region.values()
            if len(values) >= RECOVERY_CONSECUTIVE_CHECKS
            and all(item.is_up for item in values[:RECOVERY_CONSECUTIVE_CHECKS])
        )
        return recovered >= RECOVERY_QUORUM
