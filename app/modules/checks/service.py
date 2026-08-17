import time
import logging
import urllib.parse
import uuid
from datetime import datetime, timezone
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.circuit_breaker import circuit_breaker
from app.core.metrics import check_latency, checks_total
from app.core.ssrf_protection import (
    pinned_transport_for,
    resolve_pinned_target,
)
from app.modules.checks.constants import (
    CONSECUTIVE_RECOVERY_CHECKS,
    QUORUM_MIN_REGIONS,
    QUORUM_WINDOW_SECONDS,
)
from app.modules.checks.models import CheckResult
from app.modules.checks.repository import CheckRepository
from app.modules.checks.schemas import CheckResultResponse
from app.modules.dependencies.models import Dependency
from app.modules.dependencies.repository import DependencyRepository
from app.modules.dependencies.service import dependency_service

logger = logging.getLogger(__name__)

# FIX 2: module-level pooled HTTP client — one pool shared by every check
# instead of a fresh httpx.AsyncClient() (and fresh TCP/TLS handshakes) per
# probe. Used for IP-literal targets; hostname targets use the pinned
# transports from ssrf_protection (which keep their own pooled connections).
_http_client: httpx.AsyncClient | None = None

# Maximum redirect hops followed by a single check.
_MAX_REDIRECTS = 5


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=100, max_keepalive_connections=20
            ),
            timeout=httpx.Timeout(30.0),
        )
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


class CheckService:
    def __init__(
        self,
        repository: CheckRepository = CheckRepository(),
        dep_repository: DependencyRepository = DependencyRepository(),
    ) -> None:
        self.repository = repository
        self.dep_repository = dep_repository

    @staticmethod
    async def _enqueue_observation_outbox(
        session: AsyncSession,
        result: CheckResult,
        endpoint_url: str,
        method: str,
    ) -> None:
        """FIX 9: transactional outbox for the observation dual-write.

        The observation is written to ``observation_outbox`` in the SAME
        transaction as the check result. A separate Celery task
        (``app.modules.observations.tasks.process_outbox``) drains the outbox
        every 10s — the evidence stream can never silently lose events, and a
        failing observation write can never roll back the check result.
        """
        from app.modules.observations.models import OutboxEvent
        from app.modules.observations.schemas import ObservationCreateDTO

        error_type = None
        if result.error_message:
            error_type = (
                result.error_message.split(":", 1)[0]
                .strip()
                .lower()
                .replace(" ", "_")[:50]
            )
        dto = ObservationCreateDTO(
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
        )
        event = OutboxEvent(
            event_type="observation_created",
            payload=dto.model_dump_json(),
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        await session.flush()

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
        """FIX 1/4: enqueue due dependencies into the Redis ZSET queue.

        This method NEVER performs HTTP requests and NEVER updates rows in
        the database: it reads at most 500 due dependencies and adds a
        ``(next_check_timestamp, dependency_id, region)`` entry per region to
        ``reliastra:check_queue``. The scheduler poller fires
        ``execute_check.delay(...)`` when an entry becomes due, and advances
        ``next_check_at`` afterwards in its own fast transaction.
        """
        from app.infrastructure.scheduler import enqueue_check

        due_deps = await self.dep_repository.get_due_dependencies(session, limit=500)
        enqueued = 0
        for dep in due_deps:
            regions = dep.regions or ["us-east", "eu-west"]
            due_at = dep.next_check_at or datetime.now(timezone.utc)
            for region in regions:
                if await enqueue_check(str(dep.id), region, due_at):
                    enqueued += 1

        logger.info(
            "Enqueued %s checks across %s due dependencies",
            enqueued,
            len(due_deps),
        )
        return enqueued

    async def _record_blocked_result(
        self,
        session: AsyncSession,
        dep_id: uuid.UUID,
        org_id: uuid.UUID,
        region: str,
        url: str,
        method: str,
        reason: str,
    ) -> CheckResult:
        result = await self.repository.create(
            session=session,
            dependency_id=dep_id,
            org_id=org_id,
            region=region,
            latency_ms=0.0,
            is_up=False,
            status_code=None,
            error_message=f"URL blocked by security policy: {reason}",
            quorum_confirmed=False,
        )
        await self._enqueue_observation_outbox(session, result, url, method)
        return result

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

        # SSRF protection: block requests to private/internal IPs and pin the
        # connection to a validated public IP (FIX 26 — DNS-rebinding safe).
        try:
            pinned_target = resolve_pinned_target(url)
        except ValueError as exc:
            logger.warning("SSRF check blocked URL for dep %s: %s", dependency_id, exc)
            result = await self._record_blocked_result(
                session, dependency_id, dep_dto.org_id, region, url, method, str(exc)
            )
            checks_total.labels(region=region, status="blocked").inc()
            await circuit_breaker.record_failure(dependency_id)
            return result

        start_time = time.time()
        try:
            # Redirects are followed manually instead of via httpx
            # (follow_redirects) so that EVERY hop is re-validated against
            # the SSRF policy and pinned to a freshly validated IP (FIX 26).
            # Vendor endpoints routinely redirect (http->https, www->apex,
            # CDN routing); blindly following them with a pinned transport
            # would silently send cross-host requests to the wrong IP. The
            # hop cap makes a redirect loop a failed check, not an unbounded
            # request.
            redirects_followed = 0
            current_url = url
            current_target = pinned_target
            redirect_error: str | None = None
            while True:
                transport = pinned_transport_for(current_target)
                async with httpx.AsyncClient(
                    transport=transport, timeout=timeout
                ) as client:
                    response = await client.request(
                        method=method,
                        url=current_url,
                        headers=headers,
                    )
                if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                    if redirects_followed >= _MAX_REDIRECTS:
                        redirect_error = f"Too many redirects (> {_MAX_REDIRECTS})"
                        break
                    next_url = urllib.parse.urljoin(
                        current_url, response.headers["location"]
                    )
                    try:
                        current_target = resolve_pinned_target(next_url)
                    except ValueError as exc:
                        redirect_error = f"Redirect blocked by security policy: {exc}"
                        break
                    current_url = next_url
                    redirects_followed += 1
                    continue
                break

            latency_ms = (time.time() - start_time) * 1000.0
            status_code = response.status_code
            if redirect_error:
                is_up = False
                error_message = redirect_error
            elif response.status_code in expected_codes:
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

        # FIX 3: atomic quorum evaluation. Lock the dependency row so
        # concurrent checks for the same dependency serialize here and cannot
        # interleave "read recent results" with "write quorum status".
        lock_stmt = (
            select(Dependency)
            .where(Dependency.id == dependency_id)
            .with_for_update()
        )
        await session.execute(lock_stmt)

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

        await self._enqueue_observation_outbox(session, result, url, method)

        # FIX 8: feed the circuit breaker so dead dependencies stop consuming
        # worker capacity (fails open when Redis is unavailable).
        if is_up:
            await circuit_breaker.record_success(dependency_id)
        else:
            await circuit_breaker.record_failure(dependency_id)

        # FIX 12: Prometheus instrumentation.
        checks_total.labels(
            region=region, status="up" if is_up else "down"
        ).inc()
        check_latency.labels(region=region).observe(latency_ms / 1000.0)

        return result


check_service = CheckService()
