import logging
import uuid
from typing import Any
from app.infrastructure.celery_app import celery_app
from app.modules.checks.tasks import run_async
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.incidents.tasks.create_incident")
def create_incident(
    dependency_id: str,
    check_id: str | None = None,
    error_message: str = "Quorum confirmed failure",
) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        session_maker = get_session_maker()
        async with session_maker() as session:
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
                await session.commit()
                return {"incident_id": str(incident.id), "status": incident.status}
            except Exception as exc:
                await session.rollback()
                logger.exception("Error in create_incident task: %s", exc)
                return None

    return run_async(_run())


@celery_app.task(name="app.modules.incidents.tasks.resolve_incident")
def resolve_incident(dependency_id: str) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        session_maker = get_session_maker()
        async with session_maker() as session:
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
                await session.commit()
                return {"incident_id": str(updated.id), "status": updated.status}
            except Exception as exc:
                await session.rollback()
                logger.exception("Error in resolve_incident task: %s", exc)
                return None

    return run_async(_run())
