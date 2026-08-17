import logging
from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.vendors.tasks.seed_vendors")
def seed_vendors_task() -> int:
    async def _run(session) -> int:
        try:
            from app.modules.vendors.service import vendor_service

            return await vendor_service.seed_vendors(session)
        except Exception as exc:
            logger.exception("Error seeding vendors: %s", exc)
            return 0

    return async_task_body(_run)
