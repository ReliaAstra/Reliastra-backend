import logging
import uuid
from typing import Any
from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.modules.evidence.tasks.generate_evidence_report",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=180,
    time_limit=240,
)
def generate_evidence_report(
    incident_id: str, request_id: str | None = None
) -> dict[str, Any] | None:
    async def _run(session) -> dict[str, Any] | None:
        try:
            from app.modules.evidence.service import evidence_service
            report = await evidence_service.generate_for_incident(
                session, uuid.UUID(incident_id)
            )
            return {
                "id": str(report.id),
                "checksum": report.checksum,
                "file_path": report.file_path,
            }
        except Exception:
            logger.exception(
                "Error in generate_evidence_report task for incident %s "
                "(request_id=%s)",
                incident_id,
                request_id,
            )
            raise

    return async_task_body(_run)
