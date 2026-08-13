import math
from collections import Counter
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attribution.models import AttributionResult
from app.modules.incidents.repository import IncidentRepository


class AttributionEngine:
    """Deterministic multi-signal attribution engine. No AI is involved."""

    WEIGHTS = {
        "temporal": 0.20,
        "endpoint_overlap": 0.25,
        "latency_correlation": 0.25,
        "error_pattern": 0.15,
        "infrastructure_baseline": 0.15,
    }
    METHODOLOGY_VERSION = "v1.0"

    async def compute_attribution(
        self,
        session: AsyncSession,
        incident: Any,
        observations: Sequence[Any],
        infrastructure_ok: bool = True,
    ) -> AttributionResult:
        """Compute five normalized signals and a reproducible confidence score."""
        scores = {
            "temporal": await self._signal_temporal(session, incident),
            "endpoint_overlap": await self._signal_endpoint_overlap(
                session, incident
            ),
            "latency_correlation": self._signal_latency_correlation(
                observations
            ),
            "error_pattern": self._signal_error_pattern(observations),
            "infrastructure_baseline": 1.0 if infrastructure_ok else 0.0,
        }
        scores = {name: round(value, 4) for name, value in scores.items()}
        confidence = round(
            sum(scores[name] * self.WEIGHTS[name] for name in self.WEIGHTS)
            * 100,
            2,
        )
        if confidence >= 75:
            classification = "vendor_failure"
        elif confidence >= 50:
            classification = "multi_cause"
        elif not infrastructure_ok:
            classification = "infrastructure_issue"
        else:
            classification = "unknown"

        return AttributionResult(
            incident_id=incident.id,
            org_id=incident.org_id,
            suspected_dependency_id=incident.dependency_id,
            classification=classification,
            confidence_score=confidence,
            signal_breakdown=scores,
            supporting_evidence=self._collect_supporting(
                observations, scores
            ),
            contradicting_evidence=self._collect_contradicting(scores),
            methodology_version=self.METHODOLOGY_VERSION,
        )

    async def _signal_temporal(
        self, session: AsyncSession, incident: Any
    ) -> float:
        others = await IncidentRepository.list_open_in_window(
            session,
            incident.org_id,
            incident.started_at,
            window_seconds=300,
            exclude_incident_id=incident.id,
        )
        return 1.0 if others else 0.0

    async def _signal_endpoint_overlap(
        self, session: AsyncSession, incident: Any
    ) -> float:
        correlations = await IncidentRepository.get_correlations(
            session, incident.id
        )
        if not correlations:
            return 0.0
        # Manual and temporal correlations carry their pre-computed confidence.
        return min(
            1.0,
            max(float(item.correlation_confidence) for item in correlations),
        )

    @staticmethod
    def _signal_latency_correlation(observations: Sequence[Any]) -> float:
        """Score latency instability using a bounded coefficient of variation."""
        latencies = [
            max(0.0, float(item.latency_ms))
            for item in observations
            if item is not None and item.latency_ms is not None
        ]
        if len(latencies) < 2:
            return 0.0
        mean = sum(latencies) / len(latencies)
        variance = sum((value - mean) ** 2 for value in latencies) / len(
            latencies
        )
        coefficient = math.sqrt(variance) / (mean + 1.0)
        return min(1.0, max(0.0, coefficient))

    @staticmethod
    def _signal_error_pattern(observations: Sequence[Any]) -> float:
        errors = [
            str(item.error_type)
            for item in observations
            if item is not None and item.error_type
        ]
        if not errors:
            return 0.0
        counts = Counter(errors)
        # A single dominant error pattern across regions strongly supports a
        # shared external cause; mixed failures reduce the score.
        return max(counts.values()) / len(errors)

    @staticmethod
    def _collect_supporting(
        observations: Sequence[Any], scores: dict[str, float]
    ) -> list[dict[str, Any]]:
        evidence = [
            {
                "observation_id": str(item.id),
                "timestamp": item.timestamp.isoformat(),
                "region": item.region,
                "error_type": item.error_type,
            }
            for item in observations
            if item is not None
            and (item.error_type is not None or item.status_code is None)
        ]
        for signal, score in scores.items():
            if score >= 0.5:
                evidence.append(
                    {"type": "signal", "signal": signal, "score": score}
                )
        return evidence

    @staticmethod
    def _collect_contradicting(
        scores: dict[str, float]
    ) -> list[dict[str, Any]]:
        return [
            {"type": "signal", "signal": signal, "score": score}
            for signal, score in scores.items()
            if score < 0.5
        ]


attribution_engine = AttributionEngine()
