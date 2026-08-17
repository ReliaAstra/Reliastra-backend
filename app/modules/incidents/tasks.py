import logging
import uuid
from typing import Any
from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.incidents.tasks.create_incident")
def create_incident(
    dependency_id: str,
    check_id: str | None = None,
    error_message: str = "Quorum confirmed failure",
    request_id: str | None = None,
) -> dict[str, Any] | None:
    async def _run(session) -> dict[str, Any] | None:
        try:
            from app.modules.dependencies.repository import DependencyRepository
            from app.modules.incidents.service import incident_service

            dep = await DependencyRepository.get_by_id(
                session, uuid.UUID(dependency_id)
            )
            if not dep:
                return None
            incident = await incident_service.check_and_create_incident(
                session=session,
                org_id=dep.org_id,
                dependency_id=dep.id,
                error_message=error_message,
            )
            return {"incident_id": str(incident.id), "status": incident.status}
        except Exception as exc:
            logger.exception(
                "Error in create_incident task (request_id=%s): %s",
                request_id,
                exc,
            )
            return None

    return async_task_body(_run)


@celery_app.task(name="app.modules.incidents.tasks.resolve_incident")
def resolve_incident(
    dependency_id: str, request_id: str | None = None
) -> dict[str, Any] | None:
    async def _run(session) -> dict[str, Any] | None:
        try:
            from app.modules.incidents.repository import IncidentRepository
            from app.modules.incidents.service import incident_service

            open_inc = await IncidentRepository.get_open_for_dependency(
                session, uuid.UUID(dependency_id)
            )
            if not open_inc:
                return None
            updated = await incident_service.resolve_incident(
                session=session,
                incident_id=open_inc.id,
                org_id=open_inc.org_id,
            )
            return {"incident_id": str(updated.id), "status": updated.status}
        except Exception as exc:
            logger.exception(
                "Error in resolve_incident task (request_id=%s): %s",
                request_id,
                exc,
            )
            return None

    return async_task_body(_run)
