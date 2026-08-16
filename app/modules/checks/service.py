import time
import logging
import uuid
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.ssrf_protection import validate_outbound_url
from app.modules.checks.constants import (
    CONSECUTIVE_RECOVERY_CHECKS,
    QUORUM_MIN_REGIONS,
    QUORUM_WINDOW_SECONDS,
)
from app.modules.checks.models import CheckResult
from app.modules.checks.repository import CheckRepository
from app.modules.checks.schemas import CheckResultResponse
from app.modules.dependencies.repository import DependencyRepository
from app.modules.dependencies.service import dependency_service

logger = logging.getLogger(__name__)


class CheckService:
    def __init__(
        self,
        repository: CheckRepository = CheckRepository(),
        dep_repository: DependencyRepository = DependencyRepository(),
    ) -> None:
        self.repository = repository
        self.dep_repository = dep_repository

    async def _record_observation(
        self,
        session: AsyncSession,
        result: CheckResult,
        endpoint_url: str,
        method: str,
    ) -> None:
        """Dual-write a check into the unified immutable observation stream.

        A savepoint isolates the legacy check write from an observation failure,
        which keeps rollout backward compatible while still surfacing failures.
        """
        try:
            from app.modules.observations.schemas import ObservationCreateDTO
            from app.modules.observations.service import observation_service

            error_type = None
            if result.error_message:
                error_type = (
                    result.error_message.split(":", 1)[0]
                    .strip()
                    .lower()
                    .replace(" ", "_")[:50]
                )
            async with session.begin_nested():
                await observation_service.record_observation(
                    session,
                    ObservationCreateDTO(
                        timestamp=result.executed_at,
                        source_type="customer_check",
                        source_id=result.dependency_id,
                        org_id=result.org_id,
                        region=result.region,
                        endpoint_url=endpoint_url,
                        latency_ms=result.latency_ms,
                        response_time_ms=result.latency_ms,
                        status_code=result.status_code,
                        error_type=error_type,
                        error_message=result.error_message,
                        metadata={
                            "method": method,
                            "is_up": result.is_up,
                            "quorum_confirmed": result.quorum_confirmed,
                            "check_result_id": str(result.id),
                        },
                    ),
                )
        except Exception as exc:
            logger.warning(
                "Failed to record observation for dependency %s: %s",
                result.dependency_id,
                exc,
            )

    async def list_results_for_dependency(
        self,
        session: AsyncSession,
        dependency_id: uuid.UUID,
        limit: int = 50,
    ) -> list[CheckResultResponse]:
        results = await self.repository.list_for_dependency(
            session, dependency_id, limit=limit
        )
        return [CheckResultResponse.model_validate(r) for r in results]

    async def list_results_for_org(
        self, session: AsyncSession, org_id: uuid.UUID, limit: int = 50
    ) -> list[CheckResultResponse]:
        results = await self.repository.list_for_org(session, org_id, limit=limit)
        return [CheckResultResponse.model_validate(r) for r in results]

    async def schedule_due_checks(self, session: AsyncSession) -> int:
        due_deps = await self.dep_repository.get_due_dependencies(session)
        dispatched_count = 0
        now = datetime.now(timezone.utc)

        for dep in due_deps:
            # Update next_check_at immediately to avoid re-scheduling
            dep.next_check_at = now + timedelta(seconds=dep.check_interval_seconds)
            session.add(dep)
            await session.flush()

            regions = dep.regions or ["us-east", "eu-west"]
            for reg in regions:
                try:
                    await self.execute_check(session, dep.id, reg)
                    dispatched_count += 1
                except Exception as exc:
                    logger.warning("Failed to execute check for dep %s: %s", dep.id, exc)

        logger.info("Executed %s checks across %s dependencies", dispatched_count, len(due_deps))
        return dispatched_count

    async def execute_check(
        self,
        session: AsyncSession,
        dependency_id: uuid.UUID,
        region: str,
    ) -> CheckResult | None:
        dep_dto = await dependency_service.get_dependency_config_internal(
            session, dependency_id
        )
        if not dep_dto or not dep_dto.is_active:
            return None

        method = dep_dto.method
        url = dep_dto.endpoint_url
        headers = dep_dto.headers or {}
        timeout = float(dep_dto.timeout_seconds or 10.0)
        expected_codes = (
            dep_dto.expected_status_codes
            if dep_dto.expected_status_codes
            else [200]
        )

        start_time = time.time()
        latency_ms = 0.0
        status_code: int | None = None
        is_up = False
        error_message: str | None = None

        # SSRF protection: block requests to private/internal IPs
        try:
            validate_outbound_url(url)
        except ValueError as exc:
            logger.warning("SSRF check blocked URL for dep %s: %s", dependency_id, exc)
            is_up = False
            error_message = f"URL blocked by security policy: {exc}"
            latency_ms = (time.time() - start_time) * 1000.0
            result = await self.repository.create(
                session=session,
                dependency_id=dependency_id,
                org_id=dep_dto.org_id,
                region=region,
                latency_ms=latency_ms,
                is_up=is_up,
                status_code=None,
                error_message=error_message,
                quorum_confirmed=False,
            )
            await self._record_observation(session, result, url, method)
            return result

        # Reset timer for actual HTTP request
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                )
            latency_ms = (time.time() - start_time) * 1000.0
            status_code = response.status_code
            if response.status_code in expected_codes:
                is_up = True
            else:
                is_up = False
                error_message = f"Unexpected status code: {response.status_code}"
        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000.0
            is_up = False
            error_message = str(exc)
            logger.warning("Check HTTP request failed for dep %s: %s", dependency_id, exc)

        result = await self.repository.create(
            session=session,
            dependency_id=dependency_id,
            org_id=dep_dto.org_id,
            region=region,
            latency_ms=latency_ms,
            is_up=is_up,
            status_code=status_code,
            error_message=error_message,
            quorum_confirmed=False,
        )

        # Evaluate Quorum Logic
        recent_results = await self.repository.list_recent_for_dependency(
            session, dependency_id, window_seconds=QUORUM_WINDOW_SECONDS
        )

        if not is_up:
            # Failure quorum: >= 2 distinct regions report failure in 60s
            failing_regions = {
                r.region
                for r in recent_results
                if not r.is_up
            }
            failing_regions.add(region)
            if len(failing_regions) >= QUORUM_MIN_REGIONS:
                result.quorum_confirmed = True
                session.add(result)
                await session.flush()
                from app.modules.incidents.service import incident_service

                await incident_service.check_and_create_incident(
                    session=session,
                    org_id=dep_dto.org_id,
                    dependency_id=dependency_id,
                    error_message=error_message or "Quorum confirmed failure",
                )
            else:
                logger.info(
                    "False positive or single region failure for dep %s in region %s",
                    dependency_id,
                    region,
                )
        else:
            # Success: check if open incident exists and evaluate recovery quorum
            from app.modules.incidents.repository import IncidentRepository
            open_incident = await IncidentRepository.get_open_for_dependency(
                session, dependency_id
            )
            if open_incident:
                # Check if >= 2 regions report success for 2 consecutive checks
                succeeding_regions = {
                    r.region
                    for r in recent_results[: CONSECUTIVE_RECOVERY_CHECKS * 2]
                    if r.is_up
                }
                succeeding_regions.add(region)
                if len(succeeding_regions) >= QUORUM_MIN_REGIONS:
                    from app.modules.incidents.service import incident_service

                    await incident_service.resolve_incident(
                        session=session,
                        incident_id=open_incident.id,
                        org_id=open_incident.org_id,
                    )

        await self._record_observation(session, result, url, method)
        return result


check_service = CheckService()
