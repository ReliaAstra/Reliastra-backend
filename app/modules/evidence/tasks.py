import logging
import uuid
from typing import Any
from app.infrastructure.celery_app import celery_app
from app.modules.checks.tasks import run_async
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.evidence.tasks.generate_evidence_report")
def generate_evidence_report(incident_id: str) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        session_maker = get_session_maker()
        async with session_maker() as session:
            try:
                from app.modules.evidence.service import evidence_service
                report = await evidence_service.generate_for_incident(
                    session, uuid.UUID(incident_id)
                )
                await session.commit()
                return {
                    "id": str(report.id),
                    "checksum": report.checksum,
                    "file_path": report.file_path,
                }
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "Error in generate_evidence_report task for incident %s: %s",
                    incident_id,
                    exc,
                )
                return None

    return run_async(_run())
