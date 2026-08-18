import json

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.db.session import get_db
from app.modules.evidence.repository import EvidenceSnapshotRepository

router = APIRouter(prefix="/v1/verify", tags=["Verification"])


@router.get("/{verification_id}")
async def verify_evidence(
    verification_id: str = Path(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        snapshot = await EvidenceSnapshotRepository.get_by_verification_id(
            db, verification_id
        )
    except Exception:
        # Database unreachable — return a structured error rather than 500
        return Response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
            content=json.dumps({
                "found": False,
                "error": "Verification service temporarily unavailable",
                "service_degraded": True,
            }),
        )
    if not snapshot:
        return Response(
            status_code=status.HTTP_404_NOT_FOUND,
            media_type="application/json",
            content=json.dumps({"found": False, "error": "Evidence not found"}),
        )
    return {
        "found": True,
        "incident_id": str(snapshot.incident_id),
        "dependency_id": str(snapshot.dependency_id),
        "org_id": str(snapshot.org_id),
        "time_window": {
            "start": snapshot.time_window_start.isoformat(),
            "end": snapshot.time_window_end.isoformat(),
        },
        "data_hash": snapshot.data_hash,
        "report_checksum": snapshot.report_checksum,
        "methodology_version": snapshot.methodology_version,
        "created_at": snapshot.created_at.isoformat(),
    }
