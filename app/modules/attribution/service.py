import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.modules.attribution.models import AttributionResult
from app.modules.attribution.repository import AttributionRepository
from app.modules.attribution.schemas import AttributionResultResponse
from app.modules.incidents.repository import IncidentRepository

logger = logging.getLogger(__name__)

# Version of the scoring methodology, recorded on every result.
METHODOLOGY_VERSION = "v1.0"

# Weights for each of the five deterministic signals.
SIGNAL_WEIGHTS = {
    "temporal_alignment": 0.25,
    "multi_region_consensus": 0.25,
    "error_type_consistency": 0.20,
    "historical_reliability": 0.15,
    "shared_endpoint_reuse": 0.15,
}


class AttributionService:
    def __init__(
        self,
        repository: AttributionRepository = AttributionRepository(),
        inc_repository: IncidentRepository = IncidentRepository(),
    ) -> None:
        self.repository = repository
        self.inc_repository = inc_repository

    async def compute_for_incident(
        self, session: AsyncSession, incident_id: uuid.UUID
    ) -> AttributionResultResponse:
        incident = await self.inc_repository.get_by_id(session, incident_id)
        if not incident:
            raise ResourceNotFoundException("Incident not found")

        correlations = await self.inc_repository.get_correlations(session, incident_id)

        # Deterministic signal computation (explained, immutable).
        signals = await self._compute_signals(
            session, incident_id, incident.dependency_id
        )
        evidence_chain = self._build_evidence_chain(
            incident_id=incident_id,
            dependency_id=incident.dependency_id,
            correlations=correlations,
            signals=signals,
        )
        confidence = self._score(signals)
        summary = self._summarize(confidence, incident.dependency_id)

        result = await self.repository.create(
            session=session,
            incident_id=incident_id,
            org_id=incident.org_id,
            dependency_id=incident.dependency_id,
            confidence_score=confidence,
            methodology_version=METHODOLOGY_VERSION,
            signals=signals,
            evidence_chain=evidence_chain,
            summary=summary,
        )
        return AttributionResultResponse.model_validate(result)

    async def _compute_signals(
        self,
        session: AsyncSession,
        incident_id: uuid.UUID,
        dependency_id: uuid.UUID,
    ) -> dict[str, Any]:
        incident = await self.inc_repository.get_by_id(session, incident_id)
        correlations = await self.inc_repository.get_correlations(session, incident_id)

        # 1. Temporal alignment: presence and strength of temporal correlations.
        temporal = 0.0
        if correlations:
            temporal = max(
                (c.correlation_confidence or 0.0) for c in correlations
            )

        # 2. Multi-region consensus derived from recent observations for the dep.
        multi_region = 0.0
        from app.modules.observations.repository import ObservationRepository

        obs = await ObservationRepository.list_for_dependency(
            session, dependency_id, limit=50
        )
        if obs:
            failing_regions = {o.region for o in obs if not o.is_up}
            all_regions = {o.region for o in obs}
            if all_regions:
                multi_region = min(1.0, len(failing_regions) / max(1, len(all_regions)))

        # 3. Error-type consistency among the most recent observations.
        error_consistency = 0.0
        error_types = [o.error_type for o in obs if not o.is_up and o.error_type]
        if error_types:
            dominant = max(set(error_types), key=error_types.count)
            error_consistency = error_types.count(dominant) / len(error_types)

        # 4. Historical reliability: lower baseline uptime -> higher suspicion.
        reliability = 0.5
        from app.modules.checks.repository import CheckRepository

        stats = await CheckRepository.get_aggregated_stats(
            session, dependency_id, window_hours=24 * 7
        )
        uptime = stats.get("uptime_percentage", 100.0)
        reliability = max(0.0, min(1.0, (100.0 - uptime) / 50.0))

        # 5. Shared endpoint reuse: other dependencies pointing to the same URL.
        reuse = 0.0
        try:
            from app.modules.dependencies.repository import DependencyRepository
            from app.modules.dependencies.models import Dependency

            dep = await DependencyRepository.get_by_id(session, dependency_id)
            if dep:
                same = await DependencyRepository.count_by_endpoint(
                    session, dep.endpoint_url, exclude_id=dependency_id
                )
                reuse = min(1.0, same / 3.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not compute shared-endpoint signal: %s", exc)

        return {
            "temporal_alignment": round(temporal, 4),
            "multi_region_consensus": round(multi_region, 4),
            "error_type_consistency": round(error_consistency, 4),
            "historical_reliability": round(reliability, 4),
            "shared_endpoint_reuse": round(reuse, 4),
        }

    def _build_evidence_chain(
        self,
        *,
        incident_id: uuid.UUID,
        dependency_id: uuid.UUID,
        correlations: list,
        signals: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "incident_id": str(incident_id),
            "primary_suspected_dependency": str(dependency_id),
            "methodology_version": METHODOLOGY_VERSION,
            "signals": signals,
            "correlation_count": len(correlations),
        }

    def _score(self, signals: dict[str, Any]) -> float:
        total = 0.0
        for name, weight in SIGNAL_WEIGHTS.items():
            total += weight * float(signals.get(name, 0.0))
        return round(total, 4)

    def _summarize(self, confidence: float, dependency_id: uuid.UUID) -> str:
        band = "high" if confidence >= 0.7 else ("medium" if confidence >= 0.4 else "low")
        return (
            f"Deterministic attribution (methodology {METHODOLOGY_VERSION}) assigns "
            f"{band} confidence ({confidence:.2f}) to dependency {dependency_id} "
            f"as the responsible external dependency."
        )

    async def get_for_incident(
        self, session: AsyncSession, incident_id: uuid.UUID
    ) -> AttributionResultResponse:
        result = await self.repository.get_for_incident(session, incident_id)
        if not result:
            raise ResourceNotFoundException(
                "No attribution result for this incident (run attribution first)"
            )
        return AttributionResultResponse.model_validate(result)

    async def get(
        self, session: AsyncSession, attribution_id: uuid.UUID
    ) -> AttributionResultResponse:
        result = await self.repository.get_by_id(session, attribution_id)
        if not result:
            raise ResourceNotFoundException("Attribution result not found")
        return AttributionResultResponse.model_validate(result)


attribution_service = AttributionService()
