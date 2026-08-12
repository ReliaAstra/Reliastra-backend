import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.infrastructure.storage import storage_client
from app.modules.evidence.models import EvidenceSnapshot
from app.modules.observations.repository import ObservationRepository
from app.modules.verification.repository import VerificationRepository
from app.modules.verification.schemas import (
    VerificationEvidenceResponse,
    VerificationHashResponse,
    VerificationResponse,
)


class VerificationService:
    def __init__(
        self, repository: VerificationRepository = VerificationRepository()
    ) -> None:
        self.repository = repository

    async def get_snapshot(
        self, session: AsyncSession, verification_id: str
    ) -> EvidenceSnapshot:
        snapshot = await self.repository.get_by_verification_id(session, verification_id)
        if not snapshot:
            raise ResourceNotFoundException("Evidence verification record not found")
        return snapshot

    async def verify(self, session: AsyncSession, verification_id: str) -> VerificationResponse:
        snapshot = await self.get_snapshot(session, verification_id)
        hashes_match = await self._confirm_hashes(snapshot)
        return VerificationResponse(
            verification_id=snapshot.verification_id,
            incident_id=snapshot.incident_id,
            dependency_id=snapshot.dependency_id,
            org_id=snapshot.org_id,
            time_window_start=snapshot.time_window_start,
            time_window_end=snapshot.time_window_end,
            methodology_version=snapshot.methodology_version,
            data_hash=snapshot.data_hash,
            report_checksum=snapshot.report_checksum,
            created_at=snapshot.created_at,
            hashes_match=hashes_match,
        )

    async def get_hash(self, session: AsyncSession, verification_id: str) -> VerificationHashResponse:
        snapshot = await self.get_snapshot(session, verification_id)
        return VerificationHashResponse(
            verification_id=snapshot.verification_id,
            data_hash=snapshot.data_hash,
            report_checksum=snapshot.report_checksum,
        )

    async def get_evidence(
        self, session: AsyncSession, verification_id: str
    ) -> VerificationEvidenceResponse:
        snapshot = await self.get_snapshot(session, verification_id)
        observations = []
        for obs_id in snapshot.observation_ids or []:
            try:
                parsed_id = uuid.UUID(str(obs_id))
            except (ValueError, AttributeError):
                continue
            obs = await ObservationRepository.get_by_id(session, parsed_id)
            if obs:
                observations.append(self._serialize_observation(obs))
        return VerificationEvidenceResponse(
            verification_id=snapshot.verification_id,
            incident_id=snapshot.incident_id,
            dependency_id=snapshot.dependency_id,
            time_window_start=snapshot.time_window_start,
            time_window_end=snapshot.time_window_end,
            methodology_version=snapshot.methodology_version,
            data_hash=snapshot.data_hash,
            observations=observations,
            attribution_result=snapshot.attribution_result or {},
            created_at=snapshot.created_at,
        )

    async def _confirm_hashes(self, snapshot: EvidenceSnapshot) -> bool:
        try:
            stored_json = storage_client.download_bytes(snapshot.json_evidence_path)
            import hashlib

            return hashlib.sha256(stored_json).hexdigest() == snapshot.data_hash
        except Exception:
            return False

    @staticmethod
    def _serialize_observation(obs) -> dict:
        return {
            "id": str(obs.id),
            "source_type": obs.source_type,
            "timestamp": obs.timestamp.isoformat() if obs.timestamp else None,
            "region": obs.region,
            "endpoint_url": obs.endpoint_url,
            "latency_ms": obs.latency_ms,
            "status_code": obs.status_code,
            "error_type": obs.error_type,
            "error_message": obs.error_message,
        }


verification_service = VerificationService()
